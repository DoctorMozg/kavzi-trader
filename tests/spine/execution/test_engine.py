from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.api.common.models import (
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.execution_result_schema import ExecutionResultSchema
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.risk.schemas import RiskValidationResultSchema, VolatilityRegime
from kavzi_trader.spine.state.schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)


@pytest.mark.asyncio
async def test_engine_rejects_stale(
    decision_message,
    execution_config: ExecutionConfigSchema,
) -> None:
    exchange = AsyncMock()
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    staleness_checker = StalenessChecker(execution_config)
    translator = DecisionTranslator()
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
    )

    result = await engine.execute(decision_message)

    assert result.status == "EXPIRED"
    exchange.create_order.assert_not_called()


@pytest.mark.asyncio
async def test_engine_rejects_risk(
    decision_message,
    execution_config: ExecutionConfigSchema,
) -> None:
    exchange = AsyncMock()
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    risk_validator.validate_trade = AsyncMock(
        return_value=RiskValidationResultSchema(
            is_valid=False,
            rejection_reasons=["bad risk"],
            volatility_regime=VolatilityRegime.NORMAL,
            recommended_size=Decimal(0),
            size_multiplier=Decimal(1),
            warnings=[],
            should_close_all=False,
        ),
    )
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    translator = DecisionTranslator()
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
    )

    result = await engine.execute(decision_message)

    assert result.status == "REJECTED"
    exchange.create_order.assert_not_called()


@pytest.mark.asyncio
async def test_engine_executes_filled_order(
    decision_message,
    execution_config: ExecutionConfigSchema,
    filled_order_response,
) -> None:
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(return_value=filled_order_response)
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    risk_validator.validate_trade = AsyncMock(
        return_value=RiskValidationResultSchema(
            is_valid=True,
            rejection_reasons=[],
            volatility_regime=VolatilityRegime.NORMAL,
            recommended_size=Decimal(1),
            size_multiplier=Decimal(1),
            warnings=[],
            should_close_all=False,
        ),
    )
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    translator = DecisionTranslator()
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)
    liquidation_calculator = MagicMock(spec=LiquidationCalculator)
    liquidation_calculator.estimate_liquidation_price = AsyncMock(
        return_value=Decimal("92.5"),
    )

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
        liquidation_calculator=liquidation_calculator,
    )

    result = await engine.execute(decision_message)

    assert result.status == "FILLED"
    assert result.order_id == str(filled_order_response.order_id)
    assert result.executed_qty == float(filled_order_response.executed_qty)
    assert filled_order_response.status == OrderStatus.FILLED
    assert state_manager.save_order.call_count == 3  # entry + stop-loss + take-profit
    state_manager.update_position.assert_called_once()
    stored_position = state_manager.update_position.call_args.args[0]
    assert stored_position.liquidation_price == Decimal("92.5")


@pytest.mark.asyncio
async def test_engine_records_none_liquidation_when_calculator_absent(
    decision_message,
    execution_config: ExecutionConfigSchema,
    filled_order_response,
) -> None:
    """No calculator wired = honest None, not a naive (and wrong) estimate."""
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(return_value=filled_order_response)
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    risk_validator.validate_trade = AsyncMock(
        return_value=RiskValidationResultSchema(
            is_valid=True,
            rejection_reasons=[],
            volatility_regime=VolatilityRegime.NORMAL,
            recommended_size=Decimal(1),
            size_multiplier=Decimal(1),
            warnings=[],
            should_close_all=False,
        ),
    )
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    translator = DecisionTranslator()
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
    )

    result = await engine.execute(decision_message)

    assert result.status == "FILLED"
    stored_position = state_manager.update_position.call_args.args[0]
    assert stored_position.liquidation_price is None


def test_execution_result_schema_reconciliation_defaults_false() -> None:
    """New reconciliation flag is off by default for backwards compatibility."""
    result = ExecutionResultSchema(
        decision_id="d-1",
        status="FILLED",
    )
    assert result.needs_reconciliation is False


@pytest.mark.asyncio
async def test_engine_flags_reconciliation_on_monitor_timeout(
    decision_message,
    execution_config: ExecutionConfigSchema,
) -> None:
    """Monitor returning None must surface needs_reconciliation on SUBMITTED."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    new_order_response = OrderResponseSchema(
        symbol="BTCUSDT",
        order_id=456,
        client_order_id="decision-1",
        transact_time=now,
        price=Decimal(100),
        orig_qty=Decimal(1),
        executed_qty=Decimal(0),
        status=OrderStatus.NEW,
        time_in_force=TimeInForce.GTC,
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        time=now,
    )
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(return_value=new_order_response)
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    risk_validator.validate_trade = AsyncMock(
        return_value=RiskValidationResultSchema(
            is_valid=True,
            rejection_reasons=[],
            volatility_regime=VolatilityRegime.NORMAL,
            recommended_size=Decimal(1),
            size_multiplier=Decimal(1),
            warnings=[],
            should_close_all=False,
        ),
    )
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    translator = DecisionTranslator()
    monitor = MagicMock(spec=OrderMonitor)
    monitor.wait_for_completion = AsyncMock(return_value=None)

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
    )

    result = await engine.execute(decision_message)

    assert result.status == "SUBMITTED"
    assert result.needs_reconciliation is True


def _sample_position(
    *,
    position_id: str = "pos-1",
    side: str = "LONG",
) -> PositionSchema:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert side in ("LONG", "SHORT")
    return PositionSchema(
        id=position_id,
        symbol="BTCUSDT",
        side=side,  # type: ignore[arg-type]
        quantity=Decimal("0.1"),
        entry_price=Decimal(50000),
        stop_loss=Decimal(49000),
        take_profit=Decimal(52000),
        current_stop_loss=Decimal(49000),
        management_config=PositionManagementConfigSchema(),
        leverage=1,
        opened_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_place_protective_subset_places_only_sl() -> None:
    """Regression for R1 — reconciler-driven recovery must not duplicate TP."""
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(
        return_value=OrderResponseSchema(
            symbol="BTCUSDT",
            order_id=1,
            client_order_id="c",
            transact_time=datetime(2026, 1, 1, tzinfo=UTC),
            price=Decimal(49000),
            orig_qty=Decimal("0.1"),
            executed_qty=Decimal(0),
            status=OrderStatus.NEW,
            time_in_force=TimeInForce.GTC,
            type=OrderType.STOP_MARKET,
            side=OrderSide.SELL,
        ),
    )
    state_manager = AsyncMock()
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=AsyncMock(),
        staleness_checker=MagicMock(),
        translator=DecisionTranslator(),
        monitor=MagicMock(spec=OrderMonitor),
        event_store=None,
    )

    await engine._place_protective_subset(
        _sample_position(),
        place_stop_loss=True,
        place_take_profit=False,
    )

    assert exchange.create_order.await_count == 1
    kwargs = exchange.create_order.await_args.kwargs
    assert kwargs["order_type"] == OrderType.STOP_MARKET


@pytest.mark.asyncio
async def test_place_protective_subset_propagates_errors_without_emergency_close() -> (
    None
):
    """Reconciler path must NOT auto-close on SL failure — the reconciler
    already classifies the leg as unrecoverable and operator policy governs
    what happens next.
    """
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(side_effect=RuntimeError("rate limited"))
    state_manager = AsyncMock()
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=AsyncMock(),
        staleness_checker=MagicMock(),
        translator=DecisionTranslator(),
        monitor=MagicMock(spec=OrderMonitor),
        event_store=None,
    )

    with pytest.raises(RuntimeError, match="rate limited"):
        await engine._place_protective_subset(
            _sample_position(),
            place_stop_loss=True,
            place_take_profit=False,
        )

    # Emergency-close issues a MARKET reduce-only opposite-side order; assert
    # no such follow-up was made.
    assert exchange.create_order.await_count == 1


@pytest.mark.asyncio
async def test_engine_does_not_flag_reconciliation_when_filled(
    decision_message,
    execution_config: ExecutionConfigSchema,
    filled_order_response,
) -> None:
    """FILLED path keeps needs_reconciliation at its default False."""
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(return_value=filled_order_response)
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    risk_validator.validate_trade = AsyncMock(
        return_value=RiskValidationResultSchema(
            is_valid=True,
            rejection_reasons=[],
            volatility_regime=VolatilityRegime.NORMAL,
            recommended_size=Decimal(1),
            size_multiplier=Decimal(1),
            warnings=[],
            should_close_all=False,
        ),
    )
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    translator = DecisionTranslator()
    monitor = MagicMock(spec=OrderMonitor)
    monitor.wait_for_completion = AsyncMock(return_value=filled_order_response)

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
    )

    result = await engine.execute(decision_message)

    assert result.status == "FILLED"
    assert result.needs_reconciliation is False
