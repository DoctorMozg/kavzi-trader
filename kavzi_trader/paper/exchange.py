"""Paper trading exchange client that simulates order execution."""

import logging
from decimal import Decimal
from typing import Any
from uuid import uuid4

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.api.common.models import (
    OrderFillSchema,
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.commons.time_utility import utc_now

logger = logging.getLogger(__name__)

_PROTECTIVE_ORDER_TYPES = frozenset(
    {OrderType.STOP_LOSS, OrderType.STOP_LOSS_LIMIT,
     OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_LIMIT},
)


class PaperExchangeClient(BinanceClient):
    """Binance client that simulates order execution with in-memory balance.

    Inherits all read-only market data methods from BinanceClient (get_ticker,
    get_klines, get_orderbook, etc.) which hit real Binance public endpoints.
    Order and account methods are overridden to simulate fills locally.
    """

    def __init__(
        self,
        initial_balance_usdt: Decimal = Decimal("10000"),
        commission_rate: Decimal = Decimal("0.001"),
    ) -> None:
        super().__init__(api_key="", api_secret="", testnet=False)
        self._balance_usdt = initial_balance_usdt
        self._locked_usdt = Decimal("0")
        self._commission_rate = commission_rate
        self._order_counter = 900_000_000
        self._orders: dict[int, OrderResponseSchema] = {}
        self._account_store: Any = None
        logger.info(
            "Paper exchange initialised: balance=%s USDT, commission=%s",
            initial_balance_usdt,
            commission_rate,
        )

    def set_account_store(self, account_store: Any) -> None:
        """Wire the Redis account store for balance sync after each fill."""
        self._account_store = account_store

    @property
    def balance_usdt(self) -> Decimal:
        """Current available USDT balance."""
        return self._balance_usdt

    def _next_order_id(self) -> int:
        self._order_counter += 1
        return self._order_counter

    async def _sync_balance_to_store(self) -> None:
        if self._account_store is None:
            return
        try:
            await self._account_store.update_balance(
                total_balance=self._balance_usdt + self._locked_usdt,
                available_balance=self._balance_usdt,
                locked_balance=self._locked_usdt,
            )
        except Exception:
            logger.exception("Failed to sync paper balance to Redis")

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        time_in_force: TimeInForce | None = None,
        client_order_id: str | None = None,
        stop_price: Decimal | None = None,
        iceberg_qty: Decimal | None = None,
    ) -> OrderResponseSchema:
        """Simulate order execution with instant fills."""
        if quantity is None:
            raise ExchangeError("Quantity is required for paper orders")

        order_id = self._next_order_id()
        client_oid = client_order_id or str(uuid4())
        now = utc_now()

        if order_type in _PROTECTIVE_ORDER_TYPES:
            return self._store_protective_order(
                order_id=order_id,
                client_order_id=client_oid,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price or stop_price or Decimal("0"),
                stop_price=stop_price,
                time_in_force=time_in_force or TimeInForce.GTC,
                now=now,
            )

        fill_price = price
        if fill_price is None:
            ticker = await self.get_ticker(symbol)
            fill_price = ticker.last_price
            logger.debug(
                "Paper MARKET order using ticker price %s for %s",
                fill_price,
                symbol,
            )

        self._apply_balance_change(side, quantity, fill_price)

        commission = quantity * fill_price * self._commission_rate
        fill = OrderFillSchema(
            price=fill_price,
            qty=quantity,
            commission=commission,
            commission_asset="USDT",
        )

        order = OrderResponseSchema(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_oid,
            transact_time=now,
            price=fill_price,
            orig_qty=quantity,
            executed_qty=quantity,
            status=OrderStatus.FILLED,
            time_in_force=time_in_force or TimeInForce.GTC,
            type=order_type,
            side=side,
            fills=[fill],
            time=now,
            update_time=now,
            is_working=False,
        )
        self._orders[order_id] = order

        logger.info(
            "Paper %s %s filled: qty=%s price=%s cost=%s balance=%s",
            side.value,
            symbol,
            quantity,
            fill_price,
            quantity * fill_price,
            self._balance_usdt,
        )

        await self._sync_balance_to_store()
        return order

    def _apply_balance_change(
        self,
        side: OrderSide,
        quantity: Decimal,
        fill_price: Decimal,
    ) -> None:
        if side == OrderSide.BUY:
            total_cost = quantity * fill_price * (
                Decimal("1") + self._commission_rate
            )
            if self._balance_usdt < total_cost:
                raise ExchangeError(
                    "Insufficient paper balance: need %s USDT, have %s USDT"
                    % (total_cost, self._balance_usdt),
                    code=-2010,
                )
            self._balance_usdt -= total_cost
        else:
            proceeds = quantity * fill_price * (
                Decimal("1") - self._commission_rate
            )
            self._balance_usdt += proceeds

    def _store_protective_order(
        self,
        order_id: int,
        client_order_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Decimal,
        stop_price: Decimal | None,
        time_in_force: TimeInForce,
        now: Any,
    ) -> OrderResponseSchema:
        order = OrderResponseSchema(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
            transact_time=now,
            price=price,
            orig_qty=quantity,
            executed_qty=Decimal("0"),
            status=OrderStatus.NEW,
            time_in_force=time_in_force,
            type=order_type,
            side=side,
            stop_price=stop_price,
            time=now,
            update_time=now,
            is_working=False,
        )
        self._orders[order_id] = order
        logger.debug(
            "Paper protective order stored: id=%s %s %s %s qty=%s",
            order_id,
            order_type.value,
            side.value,
            symbol,
            quantity,
        )
        return order

    async def get_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> OrderResponseSchema:
        """Look up a simulated order."""
        if order_id is not None and order_id in self._orders:
            return self._orders[order_id]

        if client_order_id is not None:
            for order in self._orders.values():
                if order.client_order_id == client_order_id:
                    return order

        raise ExchangeError(
            "Paper order not found: order_id=%s client_order_id=%s"
            % (order_id, client_order_id),
        )

    async def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> OrderResponseSchema:
        """Cancel a simulated order."""
        existing = await self.get_order(
            symbol, order_id=order_id, client_order_id=client_order_id,
        )
        cancelled = OrderResponseSchema(
            symbol=existing.symbol,
            order_id=existing.order_id,
            client_order_id=existing.client_order_id,
            transact_time=existing.transact_time,
            price=existing.price,
            orig_qty=existing.orig_qty,
            executed_qty=existing.executed_qty,
            status=OrderStatus.CANCELED,
            time_in_force=existing.time_in_force,
            type=existing.type,
            side=existing.side,
            stop_price=existing.stop_price,
            time=existing.time,
            update_time=utc_now(),
            is_working=False,
        )
        self._orders[existing.order_id] = cancelled
        logger.debug("Paper order %s cancelled", existing.order_id)
        return cancelled

    async def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> list[OrderResponseSchema]:
        """Return simulated orders with status NEW."""
        result = [
            o for o in self._orders.values()
            if o.status == OrderStatus.NEW
        ]
        if symbol is not None:
            result = [o for o in result if o.symbol == symbol]
        return result

    async def get_account_info(self) -> dict[str, Any]:
        """Return simulated account info matching Binance format."""
        return {
            "balances": [
                {
                    "asset": "USDT",
                    "free": str(self._balance_usdt),
                    "locked": str(self._locked_usdt),
                },
            ],
        }

    async def get_asset_balance(self, asset: str) -> dict[str, Any]:
        """Return simulated asset balance."""
        if asset == "USDT":
            return {
                "asset": "USDT",
                "free": str(self._balance_usdt),
                "locked": str(self._locked_usdt),
            }
        return {"asset": asset, "free": "0", "locked": "0"}
