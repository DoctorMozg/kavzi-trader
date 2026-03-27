"""Paper trading exchange client that simulates USDT-M futures execution."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.api.common.models import (
    OrderFillSchema,
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
    TickerSchema,
    TimeInForce,
)
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.state.account_store import AccountStore

logger = logging.getLogger(__name__)

_PROTECTIVE_ORDER_TYPES = frozenset(
    {
        OrderType.STOP,
        OrderType.STOP_MARKET,
        OrderType.TAKE_PROFIT,
        OrderType.TAKE_PROFIT_MARKET,
    },
)


class PaperPositionSchema(BaseModel):
    """Internal position tracking for paper futures exchange."""

    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    leverage: int
    margin: Decimal

    model_config = ConfigDict(frozen=True)


class PaperExchangeClient(BinanceClient):
    """Binance client that simulates USDT-M futures order execution.

    Inherits all read-only market data methods from BinanceClient (get_ticker,
    get_klines, get_orderbook, etc.) which hit real Binance public endpoints.
    Order and account methods are overridden to simulate fills locally.

    Tracks positions with margin-based accounting. Both LONG and SHORT
    positions are supported. Opening deducts initial margin from balance;
    closing returns margin ± PnL.
    """

    def __init__(
        self,
        initial_balance_usdt: Decimal = Decimal(10000),
        commission_rate: Decimal = Decimal("0.001"),
    ) -> None:
        super().__init__(api_key="", api_secret="", testnet=False)
        self._balance_usdt = initial_balance_usdt
        self._locked_usdt = Decimal(0)
        self._commission_rate = commission_rate
        self._order_counter = 900_000_000
        self._orders: dict[int, OrderResponseSchema] = {}
        self._positions: dict[str, PaperPositionSchema] = {}
        self._last_prices: dict[str, Decimal] = {}
        self._leverage_settings: dict[str, int] = {}
        self._margin_type_settings: dict[str, str] = {}
        self._account_store: AccountStore | None = None
        logger.info(
            "Paper futures exchange initialised: balance=%s USDT, commission=%s",
            initial_balance_usdt,
            commission_rate,
        )

    def set_account_store(self, account_store: AccountStore) -> None:
        """Wire the Redis account store for balance sync after each fill."""
        self._account_store = account_store

    @property
    def balance_usdt(self) -> Decimal:
        """Current available USDT balance."""
        return self._balance_usdt

    def _next_order_id(self) -> int:
        self._order_counter += 1
        return self._order_counter

    def _get_leverage(self, symbol: str) -> int:
        return self._leverage_settings.get(symbol, 1)

    async def get_ticker(self, symbol: str) -> TickerSchema:
        """Get ticker and cache the price for unrealized PnL computation."""
        ticker = await super().get_ticker(symbol)
        self._last_prices[symbol] = ticker.last_price
        return ticker

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
        reduce_only: bool = False,
    ) -> OrderResponseSchema:
        """Simulate futures order execution with instant fills."""
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
                price=price or stop_price or Decimal(0),
                stop_price=stop_price,
                time_in_force=time_in_force or TimeInForce.GTC,
                now=now,
                reduce_only=reduce_only,
            )

        fill_price = await self._resolve_fill_price(symbol, price)
        self._apply_balance_change(symbol, side, quantity, fill_price, reduce_only)

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
            reduce_only=reduce_only,
        )
        self._orders[order_id] = order

        logger.info(
            "Paper %s %s filled: qty=%s price=%s balance=%s",
            side.value,
            symbol,
            quantity,
            fill_price,
            self._balance_usdt,
        )

        await self._sync_balance_to_store()
        return order

    async def _resolve_fill_price(
        self,
        symbol: str,
        order_price: Decimal | None,
    ) -> Decimal:
        ticker = await self.get_ticker(symbol)
        fill_price = ticker.last_price
        if order_price is not None:
            logger.debug(
                "Paper LIMIT order for %s: order_price=%s ticker=%s (using ticker)",
                symbol,
                order_price,
                fill_price,
            )
        else:
            logger.debug(
                "Paper MARKET order using ticker price %s for %s",
                fill_price,
                symbol,
            )
        return fill_price

    def _apply_balance_change(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        fill_price: Decimal,
        reduce_only: bool = False,
    ) -> None:
        existing = self._positions.get(symbol)
        commission = quantity * fill_price * self._commission_rate

        is_closing = existing is not None and (
            (existing.side == "LONG" and side == OrderSide.SELL)
            or (existing.side == "SHORT" and side == OrderSide.BUY)
        )

        if is_closing and existing is not None:
            close_qty = min(quantity, existing.quantity)
            if existing.side == "LONG":
                pnl = (fill_price - existing.entry_price) * close_qty
            else:
                pnl = (existing.entry_price - fill_price) * close_qty

            margin_per_unit = existing.margin / existing.quantity
            returned_margin = margin_per_unit * close_qty

            self._balance_usdt += returned_margin + pnl - commission
            self._locked_usdt -= returned_margin

            remaining = existing.quantity - close_qty
            if remaining > 0:
                self._positions[symbol] = PaperPositionSchema(
                    symbol=symbol,
                    side=existing.side,
                    quantity=remaining,
                    entry_price=existing.entry_price,
                    leverage=existing.leverage,
                    margin=margin_per_unit * remaining,
                )
            else:
                del self._positions[symbol]

            logger.debug(
                "Paper close %s %s: qty=%s pnl=%s returned_margin=%s",
                existing.side,
                symbol,
                close_qty,
                pnl,
                returned_margin,
            )
        elif reduce_only:
            raise ExchangeError(
                f"reduce_only order but no position to reduce for {symbol}",
                code=-2022,
            )
        else:
            leverage = self._get_leverage(symbol)
            notional = quantity * fill_price
            initial_margin = notional / Decimal(leverage) if leverage > 0 else notional
            total_cost = initial_margin + commission

            if self._balance_usdt < total_cost:
                raise ExchangeError(
                    f"Insufficient margin: need {total_cost} USDT "
                    f"(margin={initial_margin} + commission={commission}), "
                    f"have {self._balance_usdt} USDT",
                    code=-2019,
                )

            self._balance_usdt -= total_cost
            self._locked_usdt += initial_margin

            pos_side = "LONG" if side == OrderSide.BUY else "SHORT"

            if existing is not None and existing.side == pos_side:
                total_qty = existing.quantity + quantity
                avg_price = (
                    (existing.entry_price * existing.quantity) + (fill_price * quantity)
                ) / total_qty
                self._positions[symbol] = PaperPositionSchema(
                    symbol=symbol,
                    side=pos_side,
                    quantity=total_qty,
                    entry_price=avg_price,
                    leverage=leverage,
                    margin=existing.margin + initial_margin,
                )
            else:
                self._positions[symbol] = PaperPositionSchema(
                    symbol=symbol,
                    side=pos_side,
                    quantity=quantity,
                    entry_price=fill_price,
                    leverage=leverage,
                    margin=initial_margin,
                )

            logger.debug(
                "Paper open %s %s: qty=%s margin=%s leverage=%sx",
                pos_side,
                symbol,
                quantity,
                initial_margin,
                leverage,
            )

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
        now: datetime,
        reduce_only: bool = False,
    ) -> OrderResponseSchema:
        order = OrderResponseSchema(
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
            transact_time=now,
            price=price,
            orig_qty=quantity,
            executed_qty=Decimal(0),
            status=OrderStatus.NEW,
            time_in_force=time_in_force,
            type=order_type,
            side=side,
            stop_price=stop_price,
            time=now,
            update_time=now,
            is_working=False,
            reduce_only=reduce_only,
        )
        self._orders[order_id] = order
        logger.debug(
            "Paper protective order stored: id=%s %s %s %s qty=%s reduce_only=%s",
            order_id,
            order_type.value,
            side.value,
            symbol,
            quantity,
            reduce_only,
        )
        return order

    async def get_order(
        self,
        symbol: str,  # noqa: ARG002
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
            f"Paper order not found: order_id={order_id} "
            f"client_order_id={client_order_id}",
        )

    async def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> OrderResponseSchema:
        """Cancel a simulated order."""
        existing = await self.get_order(
            symbol,
            order_id=order_id,
            client_order_id=client_order_id,
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
            reduce_only=existing.reduce_only,
        )
        self._orders[existing.order_id] = cancelled
        logger.debug("Paper order %s cancelled", existing.order_id)
        return cancelled

    async def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> list[OrderResponseSchema]:
        """Return simulated orders with status NEW."""
        result = [o for o in self._orders.values() if o.status == OrderStatus.NEW]
        if symbol is not None:
            result = [o for o in result if o.symbol == symbol]
        return result

    async def get_account_info(self) -> dict[str, Any]:
        """Return simulated futures account info."""
        unrealized_pnl = self._calculate_total_unrealized_pnl()
        positions_list: list[dict[str, str]] = [
            {
                "symbol": pos.symbol,
                "positionAmt": str(
                    pos.quantity if pos.side == "LONG" else -pos.quantity,
                ),
                "entryPrice": str(pos.entry_price),
                "leverage": str(pos.leverage),
                "unrealizedProfit": "0",
                "marginType": self._margin_type_settings.get(
                    pos.symbol,
                    "isolated",
                ),
                "isolatedMargin": str(pos.margin),
                "positionSide": "BOTH",
            }
            for pos in self._positions.values()
        ]
        return {
            "totalWalletBalance": str(self._balance_usdt + self._locked_usdt),
            "availableBalance": str(self._balance_usdt),
            "totalUnrealizedProfit": str(unrealized_pnl),
            "totalInitialMargin": str(self._locked_usdt),
            "totalMaintMargin": "0",
            "positions": positions_list,
        }

    async def get_asset_balance(self, asset: str) -> dict[str, Any]:
        """Return simulated futures asset balance."""
        if asset == "USDT":
            return {
                "asset": "USDT",
                "balance": str(self._balance_usdt + self._locked_usdt),
                "availableBalance": str(self._balance_usdt),
                "crossUnPnl": "0",
            }
        return {"asset": asset, "balance": "0", "availableBalance": "0"}

    async def futures_change_leverage(
        self,
        symbol: str,
        leverage: int,
    ) -> dict[str, Any]:
        """Store leverage setting for a symbol."""
        self._leverage_settings[symbol] = leverage
        logger.info("Paper leverage set: %s → %sx", symbol, leverage)
        return {"leverage": leverage, "symbol": symbol, "maxNotionalValue": "1000000"}

    async def futures_change_margin_type(
        self,
        symbol: str,
        margin_type: str,
    ) -> dict[str, Any] | None:
        """Store margin type setting for a symbol."""
        self._margin_type_settings[symbol] = margin_type
        logger.info("Paper margin type set: %s → %s", symbol, margin_type)
        return {"code": 200, "msg": "success"}

    async def futures_get_position_info(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return simulated position information."""
        result: list[dict[str, Any]] = []
        all_positions = list(self._positions.values())
        if symbol is not None:
            all_positions = [p for p in all_positions if p.symbol == symbol]
        for pos in all_positions:
            leverage = pos.leverage
            if pos.side == "LONG":
                liq = pos.entry_price * (Decimal(1) - Decimal(1) / Decimal(leverage))
            else:
                liq = pos.entry_price * (Decimal(1) + Decimal(1) / Decimal(leverage))
            result.append(
                {
                    "symbol": pos.symbol,
                    "positionAmt": str(
                        pos.quantity if pos.side == "LONG" else -pos.quantity,
                    ),
                    "entryPrice": str(pos.entry_price),
                    "markPrice": str(pos.entry_price),
                    "unRealizedProfit": "0",
                    "liquidationPrice": str(liq),
                    "leverage": str(leverage),
                    "marginType": self._margin_type_settings.get(
                        pos.symbol,
                        "isolated",
                    ),
                    "isolatedMargin": str(pos.margin),
                    "positionSide": "BOTH",
                },
            )
        return result

    async def futures_get_leverage_brackets(
        self,
        symbol: str | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        """Return simulated leverage bracket data."""
        return [
            {
                "symbol": "BTCUSDT",
                "brackets": [
                    {
                        "bracket": 1,
                        "initialLeverage": 125,
                        "notionalCap": 50000,
                        "notionalFloor": 0,
                        "maintMarginRatio": 0.004,
                    },
                ],
            },
        ]

    def _calculate_total_unrealized_pnl(self) -> Decimal:
        total = Decimal(0)
        for pos in self._positions.values():
            current_price = self._last_prices.get(pos.symbol)
            if current_price is None:
                continue
            if pos.side == "LONG":
                total += (current_price - pos.entry_price) * pos.quantity
            else:
                total += (pos.entry_price - current_price) * pos.quantity
        return total
