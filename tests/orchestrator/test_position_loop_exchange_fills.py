import asyncio
from decimal import Decimal
from typing import Literal, cast
from unittest.mock import AsyncMock, patch

import pytest

from kavzi_trader.api.common.models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TickerSchema,
)
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.spine.position.action_executor import PositionActionExecutor
from kavzi_trader.spine.position.exchange_fill_detector import ExchangeFillDetector
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.stall_exit import StallExitChecker
from kavzi_trader.spine.position.time_exit import TimeExitChecker
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.schemas import (
    OpenOrderSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)

Side = Literal["LONG", "SHORT"]


class _OrderStore:
    def __init__(self) -> None:
        self.by_id: dict[str, OpenOrderSchema] = {}

    async def get_by_position(self, position_id: str) -> list[OpenOrderSchema]:
        return [o for o in self.by_id.values() if o.linked_position_id == position_id]


class _InMemoryState:
    """Just the StateManager surface the position loop and executor touch."""

    def __init__(self) -> None:
        self.positions: dict[str, PositionSchema] = {}
        self.orders = _OrderStore()

    async def get_all_positions(self) -> list[PositionSchema]:
        return list(self.positions.values())

    async def get_position(self, symbol: str) -> PositionSchema | None:
        return next((p for p in self.positions.values() if p.symbol == symbol), None)

    async def update_position(self, position: PositionSchema) -> None:
        self.positions[position.id] = position

    async def remove_position(self, position_id: str) -> None:
        self.positions.pop(position_id, None)

    async def save_order(self, order: OpenOrderSchema) -> None:
        self.orders.by_id[order.order_id] = order

    async def remove_order(self, order_id: str) -> None:
        self.orders.by_id.pop(order_id, None)


class _Scenario:
    def __init__(self, side: Side) -> None:
        self.side: Side = side
        self.state = _InMemoryState()
        self.report = AsyncMock()
        with patch("kavzi_trader.api.binance.client.BinanceAPIClient"):
            self.exchange = PaperExchangeClient(
                initial_balance_usdt=Decimal(10000),
                commission_rate=Decimal("0.001"),
            )
        self.set_price(100)
        state = cast("StateManager", self.state)
        self.loop = PositionManagementLoop(
            manager=PositionManager(
                partial_exit=PartialExitChecker(),
                time_exit=TimeExitChecker(),
                stall_exit=StallExitChecker(),
                liquidation_emergency_percent=Decimal("5.0"),
            ),
            state_manager=state,
            atr_provider=AsyncMock(get_atr=AsyncMock(return_value=Decimal(2))),
            price_provider=AsyncMock(
                get_current_price=AsyncMock(side_effect=self._price),
            ),
            action_executor=PositionActionExecutor(self.exchange, state),
            fill_detector=ExchangeFillDetector(self.exchange, state),
            interval_s=5,
            report_populator=self.report,
            fill_check_interval_s=0,
        )
        self.sl_id = 0
        self.tp_id = 0

    async def _price(self, symbol: str) -> Decimal:
        return (await self.exchange.get_ticker(symbol)).last_price

    def set_price(self, price: int) -> None:
        self.exchange.get_ticker = AsyncMock(
            return_value=TickerSchema(symbol="BTCUSDT", last_price=Decimal(price)),
        )

    async def open_bracketed_position(self) -> PositionSchema:
        is_long = self.side == "LONG"
        entry_side = OrderSide.BUY if is_long else OrderSide.SELL
        exit_side = OrderSide.SELL if is_long else OrderSide.BUY
        stop, take = (
            (Decimal(95), Decimal(110)) if is_long else (Decimal(105), Decimal(90))
        )
        await self.exchange.create_order(
            "BTCUSDT", entry_side, OrderType.MARKET, quantity=Decimal(1)
        )
        now = utc_now()
        position = PositionSchema(
            id="pos-1",
            symbol="BTCUSDT",
            side=self.side,
            quantity=Decimal(1),
            entry_price=Decimal(100),
            stop_loss=stop,
            take_profit=take,
            current_stop_loss=stop,
            management_config=PositionManagementConfigSchema(),
            opened_at=now,
            updated_at=now,
        )
        await self.state.update_position(position)
        for order_type, trigger in (
            (OrderType.STOP_MARKET, stop),
            (OrderType.TAKE_PROFIT_MARKET, take),
        ):
            response = await self.exchange.create_order(
                "BTCUSDT",
                exit_side,
                order_type,
                quantity=Decimal(1),
                stop_price=trigger,
                reduce_only=True,
            )
            await self.state.save_order(
                OpenOrderSchema(
                    order_id=str(response.order_id),
                    symbol="BTCUSDT",
                    side=exit_side,
                    order_type=order_type,
                    price=trigger,
                    quantity=Decimal(1),
                    status=OrderStatus.NEW,
                    linked_position_id=position.id,
                    created_at=now,
                ),
            )
            if order_type == OrderType.STOP_MARKET:
                self.sl_id = response.order_id
            else:
                self.tp_id = response.order_id
        return position

    async def exchange_fills(self, order_id: int) -> None:
        """Let the exchange trigger one leg between two bot ticks."""
        await self.exchange.get_order("BTCUSDT", order_id=order_id)

    async def run_cycle(self) -> None:
        async with asyncio.timeout(3):
            await self.loop._manage_positions()


@pytest.mark.parametrize(
    ("side", "leg", "price", "reason", "exit_price"),
    [
        ("LONG", "sl", 94, "stop_loss_filled", Decimal(94)),
        ("LONG", "tp", 111, "take_profit_filled", Decimal(110)),
        ("SHORT", "sl", 106, "stop_loss_filled", Decimal(106)),
        ("SHORT", "tp", 89, "take_profit_filled", Decimal(90)),
    ],
)
async def test_exchange_side_fill_closes_local_position(
    side: Side,
    leg: str,
    price: int,
    reason: str,
    exit_price: Decimal,
) -> None:
    sc = _Scenario(side)
    await sc.open_bracketed_position()
    sc.set_price(price)
    await sc.exchange_fills(sc.sl_id if leg == "sl" else sc.tp_id)
    exchange_orders_before = len(sc.exchange._orders)

    await sc.run_cycle()

    assert sc.state.positions == {}
    assert sc.state.orders.by_id == {}
    assert await sc.exchange.get_open_orders("BTCUSDT") == []
    assert len(sc.exchange._orders) == exchange_orders_before, "no close retries"
    sc.report.record_position_close.assert_awaited_once()
    kwargs = sc.report.record_position_close.await_args.kwargs
    assert kwargs["close_reason"] == reason
    assert kwargs["exit_price"] == exit_price
    assert kwargs["side"] == side


async def test_position_already_gone_on_exchange_is_cleaned_up() -> None:
    sc = _Scenario("LONG")
    await sc.open_bracketed_position()
    sc.exchange._positions.clear()
    sc.set_price(101)

    await sc.run_cycle()

    assert sc.state.positions == {}
    assert sc.state.orders.by_id == {}
    assert await sc.exchange.get_open_orders("BTCUSDT") == []
    kwargs = sc.report.record_position_close.await_args.kwargs
    assert kwargs["close_reason"] == "exchange_position_closed"
    assert kwargs["exit_price"] == Decimal(101)


async def test_open_position_with_resting_bracket_is_kept() -> None:
    sc = _Scenario("LONG")
    await sc.open_bracketed_position()
    sc.set_price(102)

    await sc.run_cycle()

    assert set(sc.state.positions) == {"pos-1"}
    assert len(sc.state.orders.by_id) == 2
    sc.report.record_position_close.assert_not_awaited()


async def test_fill_check_is_rate_limited() -> None:
    sc = _Scenario("LONG")
    await sc.open_bracketed_position()
    sc.loop._fill_check_interval_s = 3600
    sc.exchange.get_order = AsyncMock(wraps=sc.exchange.get_order)

    await sc.run_cycle()
    await sc.run_cycle()

    assert sc.exchange.get_order.await_count == 2  # SL + TP, first cycle only


async def test_detector_failure_does_not_block_position_management() -> None:
    sc = _Scenario("LONG")
    await sc.open_bracketed_position()
    sc.loop._fill_detector = AsyncMock(
        detect=AsyncMock(side_effect=RuntimeError("exchange down")),
    )
    sc.set_price(94)

    await sc.run_cycle()

    # The local SL check still ran and closed the position.
    assert sc.state.positions == {}
