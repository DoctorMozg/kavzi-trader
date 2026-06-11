from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.models import (
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import (
    PendingEntrySchema,
    PositionManagementConfigSchema,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _pullback_decision() -> DecisionMessageSchema:
    return DecisionMessageSchema(
        decision_id="decision-1",
        symbol="BTCUSDT",
        action="LONG",
        entry_tactic="PULLBACK_TO_LEVEL",
        entry_price=Decimal(99),
        stop_loss=Decimal(95),
        take_profit=Decimal(107),
        quantity=Decimal(1),
        raw_confidence=0.8,
        calibrated_confidence=0.7,
        volatility_regime=VolatilityRegime.NORMAL,
        position_management=PositionManagementConfigSchema(),
        created_at_ms=1_000,
        expires_at_ms=60_000,
        current_atr=Decimal(2),
        atr_history=[Decimal("1.8"), Decimal("2.1")],
    )


def _pending_entry(expires_at_ms: int = 10_000) -> PendingEntrySchema:
    return PendingEntrySchema(
        order_id="555",
        symbol="BTCUSDT",
        decision_json=_pullback_decision().model_dump_json(),
        expires_at_ms=expires_at_ms,
    )


def _order(status: OrderStatus) -> OrderResponseSchema:
    return OrderResponseSchema(
        symbol="BTCUSDT",
        order_id=555,
        client_order_id="decision-1",
        transact_time=_NOW,
        price=Decimal(99),
        orig_qty=Decimal(1),
        executed_qty=Decimal(1) if status == OrderStatus.FILLED else Decimal(0),
        status=status,
        time_in_force=TimeInForce.GTC,
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        time=_NOW,
    )


def _engine(exchange: AsyncMock, state_manager: AsyncMock) -> ExecutionEngine:
    return ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=AsyncMock(),
        staleness_checker=AsyncMock(),
        translator=AsyncMock(),
        monitor=AsyncMock(),
        event_store=None,
    )


@pytest.mark.asyncio
async def test_sweep_protects_position_on_fill() -> None:
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value=_order(OrderStatus.FILLED))
    state_manager = AsyncMock()
    state_manager.list_pending_entries = AsyncMock(return_value=[_pending_entry()])
    engine = _engine(exchange, state_manager)
    engine._on_order_filled = AsyncMock()  # isolate sweep from open/protect internals

    await engine.process_pending_entries(now_ms=5_000)

    engine._on_order_filled.assert_awaited_once()
    await_args = engine._on_order_filled.await_args
    assert await_args is not None
    called_decision = await_args.args[0]
    assert called_decision.symbol == "BTCUSDT"
    assert called_decision.action == "LONG"
    state_manager.remove_pending_entry.assert_awaited_once_with("555")
    exchange.cancel_order.assert_not_called()


@pytest.mark.asyncio
async def test_sweep_cancels_expired_unfilled_entry() -> None:
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value=_order(OrderStatus.NEW))
    state_manager = AsyncMock()
    state_manager.list_pending_entries = AsyncMock(
        return_value=[_pending_entry(expires_at_ms=10_000)]
    )
    engine = _engine(exchange, state_manager)
    engine._on_order_filled = AsyncMock()

    await engine.process_pending_entries(now_ms=10_000)  # at deadline

    exchange.cancel_order.assert_awaited_once_with(symbol="BTCUSDT", order_id=555)
    state_manager.remove_pending_entry.assert_awaited_once_with("555")
    engine._on_order_filled.assert_not_called()


@pytest.mark.asyncio
async def test_sweep_keeps_unexpired_resting_entry() -> None:
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value=_order(OrderStatus.NEW))
    state_manager = AsyncMock()
    state_manager.list_pending_entries = AsyncMock(
        return_value=[_pending_entry(expires_at_ms=10_000)]
    )
    engine = _engine(exchange, state_manager)

    await engine.process_pending_entries(now_ms=9_999)  # one ms before deadline

    exchange.cancel_order.assert_not_called()
    state_manager.remove_pending_entry.assert_not_called()


@pytest.mark.asyncio
async def test_sweep_leaves_partial_fill_untouched() -> None:
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value=_order(OrderStatus.PARTIALLY_FILLED))
    state_manager = AsyncMock()
    state_manager.list_pending_entries = AsyncMock(
        return_value=[_pending_entry(expires_at_ms=1)]
    )
    engine = _engine(exchange, state_manager)
    engine._on_order_filled = AsyncMock()

    # Past the deadline, but a partial fill must not be cancelled (would
    # orphan the filled portion unprotected).
    await engine.process_pending_entries(now_ms=999_999)

    exchange.cancel_order.assert_not_called()
    state_manager.remove_pending_entry.assert_not_called()
    engine._on_order_filled.assert_not_called()


@pytest.mark.asyncio
async def test_sweep_drops_externally_cancelled_entry() -> None:
    exchange = AsyncMock()
    exchange.get_order = AsyncMock(return_value=_order(OrderStatus.CANCELED))
    state_manager = AsyncMock()
    state_manager.list_pending_entries = AsyncMock(return_value=[_pending_entry()])
    engine = _engine(exchange, state_manager)
    engine._on_order_filled = AsyncMock()

    await engine.process_pending_entries(now_ms=5_000)

    state_manager.remove_pending_entry.assert_awaited_once_with("555")
    exchange.cancel_order.assert_not_called()
    engine._on_order_filled.assert_not_called()


@pytest.mark.asyncio
async def test_sweep_isolates_failures_across_entries() -> None:
    # First entry's poll raises; the second must still be processed.
    good = _pending_entry()
    bad = PendingEntrySchema(
        order_id="999",
        symbol="ETHUSDT",
        decision_json=_pullback_decision().model_dump_json(),
        expires_at_ms=10_000,
    )

    async def _get_order(symbol: str, order_id: int) -> OrderResponseSchema:
        if order_id == 999:
            raise RuntimeError("exchange hiccup")
        return _order(OrderStatus.FILLED)

    exchange = AsyncMock()
    exchange.get_order = AsyncMock(side_effect=_get_order)
    state_manager = AsyncMock()
    state_manager.list_pending_entries = AsyncMock(return_value=[bad, good])
    engine = _engine(exchange, state_manager)
    engine._on_order_filled = AsyncMock()

    await engine.process_pending_entries(now_ms=5_000)

    engine._on_order_filled.assert_awaited_once()
    state_manager.remove_pending_entry.assert_awaited_once_with("555")
