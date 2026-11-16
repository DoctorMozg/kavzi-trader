"""Paper trading exchange client that simulates USDT-M futures execution."""

import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.schemas.data_dicts import (
    AccountInfoDict,
    AccountPositionDict,
    FundingRateDict,
    LeverageBracketDict,
    LeverageBracketEntryDict,
    LeverageChangeDict,
    LongShortRatioDict,
    MarginTypeChangeDict,
    OpenInterestHistDict,
    PositionInfoDict,
)
from kavzi_trader.api.common.exceptions import (
    UNKNOWN_ORDER_ERROR_CODE,
    ExchangeError,
)
from kavzi_trader.api.common.models import TickerSchema
from kavzi_trader.commons.clock import Clock
from kavzi_trader.commons.system_clock import SYSTEM_CLOCK
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.order_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.domain.order_response import OrderFillSchema, OrderResponseSchema
from kavzi_trader.domain.state_schemas import (
    AccountStateSchema,
    OpenOrderSchema,
    PositionSchema,
)
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


_TRIGGERED_ORDER_TYPES = frozenset(
    {OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET},
)


class _PaperPositionTrackerSchema(BaseModel):
    """Internal position tracking for paper futures exchange."""

    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    leverage: int
    margin: Decimal

    model_config = ConfigDict(frozen=True)


class PaperExchangeClient:
    """ExchangeClient that simulates USDT-M futures order execution.

    Market data methods delegate to a keyless BinanceClient hitting real Binance
    public endpoints. Order and account methods simulate fills locally.

    Tracks positions with margin-based accounting. Both LONG and SHORT
    positions are supported. Opening deducts initial margin from balance;
    closing returns margin ± PnL.
    """

    def __init__(
        self,
        initial_balance_usdt: Decimal = Decimal(10000),
        commission_rate: Decimal = Decimal("0.001"),
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._clock = clock
        self._market_data = BinanceClient(api_key="", api_secret="")
        self._balance_usdt = initial_balance_usdt
        self._locked_usdt = Decimal(0)
        self._commission_rate = commission_rate
        self._order_counter = 900_000_000
        self._orders: dict[int, OrderResponseSchema] = {}
        self._positions: dict[str, _PaperPositionTrackerSchema] = {}
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

    def restore_from_state(
        self,
        account: AccountStateSchema,
        positions: list[PositionSchema],
        open_orders: list[OpenOrderSchema],
    ) -> None:
        """Rebuild the in-memory book from persisted state after a restart."""
        self._balance_usdt = account.available_balance_usdt
        self._locked_usdt = account.locked_balance_usdt
        self._positions = {p.symbol: self._tracker_from_position(p) for p in positions}
        self._orders = {}
        for stored in open_orders:
            if stored.order_type not in _PROTECTIVE_ORDER_TYPES:
                logger.warning(
                    "Paper restore skipped non-protective order %s (%s)",
                    stored.order_id,
                    stored.order_type.value,
                )
                continue
            order_id = int(stored.order_id)
            self._orders[order_id] = OrderResponseSchema(
                symbol=stored.symbol,
                order_id=order_id,
                client_order_id=f"restored-{order_id}",
                transact_time=stored.created_at,
                price=stored.price,
                orig_qty=stored.quantity,
                executed_qty=stored.executed_qty,
                status=OrderStatus.NEW,
                time_in_force=TimeInForce.GTC,
                type=stored.order_type,
                side=stored.side,
                # Protective orders keep their trigger in the stored price.
                stop_price=stored.price,
                time=stored.created_at,
                update_time=stored.created_at,
                is_working=False,
                reduce_only=True,
            )
        if self._orders:
            self._order_counter = max(self._order_counter, *self._orders)
        logger.info(
            "Paper state restored: balance=%s locked=%s positions=%d orders=%d",
            self._balance_usdt,
            self._locked_usdt,
            len(self._positions),
            len(self._orders),
        )

    @staticmethod
    def _tracker_from_position(position: PositionSchema) -> _PaperPositionTrackerSchema:
        margin = position.initial_margin or (
            position.quantity * position.entry_price / Decimal(position.leverage)
        )
        return _PaperPositionTrackerSchema(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            leverage=position.leverage,
            margin=margin,
        )

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
        ticker = await self._market_data.get_ticker(symbol)
        self._last_prices[symbol] = ticker.last_price
        return ticker

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
        limit: int = 500,
    ) -> list[CandlestickSchema]:
        return await self._market_data.get_klines(
            symbol, interval, start_time, end_time, limit
        )

    async def get_funding_rate(
        self,
        symbol: str,
        limit: int = 100,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[FundingRateDict]:
        return await self._market_data.get_funding_rate(
            symbol, limit, start_time, end_time
        )

    async def get_open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[OpenInterestHistDict]:
        return await self._market_data.get_open_interest_history(
            symbol, period, limit, start_time, end_time
        )

    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[LongShortRatioDict]:
        return await self._market_data.get_long_short_ratio(
            symbol, period, limit, start_time, end_time
        )

    async def close(self) -> None:
        await self._market_data.close()

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
        now = self._clock.now()

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

        if (
            order_type == OrderType.LIMIT
            and price is not None
            and not reduce_only
            and not await self._limit_is_marketable(symbol, side, price)
        ):
            # Entry limit resting away from price (e.g. a pullback): sits NEW
            # until the ticker crosses it. The pending-entry sweep polls it.
            return self._store_resting_limit(
                order_id=order_id,
                client_order_id=client_oid,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                time_in_force=time_in_force or TimeInForce.GTC,
                now=now,
            )

        fill_price = await self._resolve_fill_price(symbol, price)
        existing = self._positions.get(symbol)
        if reduce_only and existing is not None:
            # A reduce-only order never fills past the open position.
            quantity = min(quantity, existing.quantity)
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

    async def _limit_is_marketable(
        self,
        symbol: str,
        side: OrderSide,
        price: Decimal,
    ) -> bool:
        """True when a LIMIT can fill immediately against the current ticker.

        A BUY fills now when the market is at or below its price; a SELL when
        the market is at or above its price. Otherwise the limit rests.
        """
        ticker = await self.get_ticker(symbol)
        if side == OrderSide.BUY:
            return ticker.last_price <= price
        return ticker.last_price >= price

    def _store_resting_limit(
        self,
        order_id: int,
        client_order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        time_in_force: TimeInForce,
        now: datetime,
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
            type=OrderType.LIMIT,
            side=side,
            time=now,
            update_time=now,
            is_working=True,
            reduce_only=False,
        )
        self._orders[order_id] = order
        logger.info(
            "Paper resting LIMIT stored: id=%s %s %s qty=%s price=%s",
            order_id,
            side.value,
            symbol,
            quantity,
            price,
        )
        return order

    async def _maybe_fill_resting_limit(
        self,
        order: OrderResponseSchema,
    ) -> OrderResponseSchema:
        """Fill a resting entry limit if the ticker has crossed its price.

        Fills happen at the limit price (a realistic touch fill). Protective
        and reduce-only orders are never touched by this path.
        """
        if (
            order.status != OrderStatus.NEW
            or order.type != OrderType.LIMIT
            or order.reduce_only
        ):
            return order
        if not await self._limit_is_marketable(order.symbol, order.side, order.price):
            return order

        fill_price = order.price
        self._apply_balance_change(
            order.symbol, order.side, order.orig_qty, fill_price, reduce_only=False
        )
        commission = order.orig_qty * fill_price * self._commission_rate
        fill = OrderFillSchema(
            price=fill_price,
            qty=order.orig_qty,
            commission=commission,
            commission_asset="USDT",
        )
        filled = order.model_copy(
            update={
                "status": OrderStatus.FILLED,
                "executed_qty": order.orig_qty,
                "fills": [fill],
                "update_time": self._clock.now(),
                "is_working": False,
            },
        )
        self._orders[order.order_id] = filled
        logger.info(
            "Paper resting LIMIT %s filled for %s at %s",
            order.order_id,
            order.symbol,
            fill_price,
        )
        await self._sync_balance_to_store()
        return filled

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
                self._positions[symbol] = _PaperPositionTrackerSchema(
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
                self._positions[symbol] = _PaperPositionTrackerSchema(
                    symbol=symbol,
                    side=pos_side,
                    quantity=total_qty,
                    entry_price=avg_price,
                    leverage=leverage,
                    margin=existing.margin + initial_margin,
                )
            else:
                self._positions[symbol] = _PaperPositionTrackerSchema(
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
        """Look up a simulated order, lazily filling resting orders on cross."""
        order = self._find_order(order_id, client_order_id)
        return await self._maybe_fill_resting_order(order)

    def _find_order(
        self,
        order_id: int | None,
        client_order_id: str | None,
    ) -> OrderResponseSchema:
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

    async def _maybe_fill_resting_order(
        self,
        order: OrderResponseSchema,
    ) -> OrderResponseSchema:
        if order.type in _TRIGGERED_ORDER_TYPES:
            return await self._maybe_fill_triggered_order(order)
        return await self._maybe_fill_resting_limit(order)

    async def _maybe_fill_triggered_order(
        self,
        order: OrderResponseSchema,
    ) -> OrderResponseSchema:
        """Fill a resting STOP_MARKET / TAKE_PROFIT_MARKET once price crosses it.

        Stops fill at the worse of trigger and current price (a real stop-market
        slips through gaps); take-profits fill at the trigger so a favourable
        gap never inflates paper PnL.
        """
        if order.status != OrderStatus.NEW or order.stop_price is None:
            return order

        if order.symbol not in self._positions:
            # Real Binance drops reduce-only orders once the position is flat.
            return self._cancel_orphaned_order(order)

        ticker = await self.get_ticker(order.symbol)
        last_price = ticker.last_price
        is_stop = order.type == OrderType.STOP_MARKET
        # A SELL stop / BUY take-profit triggers on a falling price, and vice versa.
        triggers_below = (order.side == OrderSide.SELL) == is_stop
        crossed = (
            last_price <= order.stop_price
            if triggers_below
            else last_price >= order.stop_price
        )
        if not crossed:
            return order

        if not is_stop:
            fill_price = order.stop_price
        elif order.side == OrderSide.SELL:
            fill_price = min(order.stop_price, last_price)
        else:
            fill_price = max(order.stop_price, last_price)

        position = self._positions[order.symbol]
        fill_qty = min(order.orig_qty, position.quantity)
        self._apply_balance_change(
            order.symbol, order.side, fill_qty, fill_price, reduce_only=True
        )
        fill = OrderFillSchema(
            price=fill_price,
            qty=fill_qty,
            commission=fill_qty * fill_price * self._commission_rate,
            commission_asset="USDT",
        )
        filled = order.model_copy(
            update={
                "status": OrderStatus.FILLED,
                "executed_qty": fill_qty,
                "avg_price": fill_price,
                "fills": [fill],
                "update_time": self._clock.now(),
                "is_working": False,
            },
        )
        self._orders[order.order_id] = filled
        logger.info(
            "Paper %s %s triggered for %s: trigger=%s last=%s fill=%s",
            order.type.value,
            order.order_id,
            order.symbol,
            order.stop_price,
            last_price,
            fill_price,
        )
        await self._sync_balance_to_store()
        return filled

    def _cancel_orphaned_order(self, order: OrderResponseSchema) -> OrderResponseSchema:
        cancelled = order.model_copy(
            update={
                "status": OrderStatus.CANCELED,
                "update_time": self._clock.now(),
                "is_working": False,
            },
        )
        self._orders[order.order_id] = cancelled
        logger.info(
            "Paper protective order %s cancelled: no position left for %s",
            order.order_id,
            order.symbol,
        )
        return cancelled

    async def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> OrderResponseSchema:
        """Cancel a simulated order; filled orders raise like Binance's -2011."""
        existing = await self.get_order(
            symbol,
            order_id=order_id,
            client_order_id=client_order_id,
        )
        if existing.status == OrderStatus.FILLED:
            raise ExchangeError(
                f"Unknown order sent: order {existing.order_id} already filled",
                code=UNKNOWN_ORDER_ERROR_CODE,
            )
        cancelled = existing.model_copy(
            update={
                "status": OrderStatus.CANCELED,
                "update_time": self._clock.now(),
                "is_working": False,
            },
        )
        self._orders[existing.order_id] = cancelled
        logger.debug("Paper order %s cancelled", existing.order_id)
        return cancelled

    async def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> list[OrderResponseSchema]:
        """Return simulated orders with status NEW, triggering crossed ones first."""
        for order in list(self._orders.values()):
            if order.type in _TRIGGERED_ORDER_TYPES:
                await self._maybe_fill_triggered_order(order)
        result = [o for o in self._orders.values() if o.status == OrderStatus.NEW]
        if symbol is not None:
            result = [o for o in result if o.symbol == symbol]
        return result

    async def get_account_info(self) -> AccountInfoDict:
        """Return simulated futures account info."""
        unrealized_pnl = self._calculate_total_unrealized_pnl()
        positions_list: list[AccountPositionDict] = [
            AccountPositionDict(
                symbol=pos.symbol,
                positionAmt=str(
                    pos.quantity if pos.side == "LONG" else -pos.quantity,
                ),
                entryPrice=str(pos.entry_price),
                leverage=str(pos.leverage),
                unrealizedProfit="0",
                marginType=self._margin_type_settings.get(
                    pos.symbol,
                    "isolated",
                ),
                isolatedMargin=str(pos.margin),
                positionSide="BOTH",
            )
            for pos in self._positions.values()
        ]
        return AccountInfoDict(
            totalWalletBalance=str(self._balance_usdt + self._locked_usdt),
            availableBalance=str(self._balance_usdt),
            totalUnrealizedProfit=str(unrealized_pnl),
            totalInitialMargin=str(self._locked_usdt),
            totalMaintMargin="0",
            positions=positions_list,
        )

    async def futures_change_leverage(
        self,
        symbol: str,
        leverage: int,
    ) -> LeverageChangeDict:
        """Store leverage setting for a symbol."""
        self._leverage_settings[symbol] = leverage
        logger.info("Paper leverage set: %s → %sx", symbol, leverage)
        return LeverageChangeDict(
            leverage=leverage,
            symbol=symbol,
            maxNotionalValue="1000000",
        )

    async def futures_change_margin_type(
        self,
        symbol: str,
        margin_type: str,
    ) -> MarginTypeChangeDict | None:
        """Store margin type setting for a symbol."""
        self._margin_type_settings[symbol] = margin_type
        logger.info("Paper margin type set: %s → %s", symbol, margin_type)
        return MarginTypeChangeDict(code=200, msg="success")

    async def futures_get_position_info(
        self,
        symbol: str | None = None,
    ) -> list[PositionInfoDict]:
        """Return simulated position information."""
        result: list[PositionInfoDict] = []
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
                PositionInfoDict(
                    symbol=pos.symbol,
                    positionAmt=str(
                        pos.quantity if pos.side == "LONG" else -pos.quantity,
                    ),
                    entryPrice=str(pos.entry_price),
                    markPrice=str(pos.entry_price),
                    unRealizedProfit="0",
                    liquidationPrice=str(liq),
                    leverage=str(leverage),
                    marginType=self._margin_type_settings.get(
                        pos.symbol,
                        "isolated",
                    ),
                    isolatedMargin=str(pos.margin),
                    positionSide="BOTH",
                ),
            )
        return result

    async def futures_get_leverage_brackets(
        self,
        symbol: str | None = None,  # noqa: ARG002
    ) -> list[LeverageBracketDict]:
        """Return simulated leverage bracket data."""
        return [
            LeverageBracketDict(
                symbol="BTCUSDT",
                brackets=[
                    LeverageBracketEntryDict(
                        bracket=1,
                        initialLeverage=125,
                        notionalCap=50000,
                        notionalFloor=0,
                        maintMarginRatio=0.004,
                        cum=0.0,
                    ),
                ],
            ),
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
