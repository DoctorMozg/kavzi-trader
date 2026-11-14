from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.domain.execution_result import ExecutionResultSchema
from kavzi_trader.domain.order_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.domain.state_schemas import (
    AccountStateSchema,
    OpenOrderSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.events.config import EventStoreConfigSchema
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.risk.schemas import RiskValidationResultSchema
from kavzi_trader.spine.risk.validator import DynamicRiskValidator


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
async def test_engine_events_land_in_configured_streams(
    decision_message,
    filled_order_response,
) -> None:
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(return_value=filled_order_response)
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
    redis_client = MagicMock()
    redis_client.client.xadd = AsyncMock(return_value="1-0")
    config = EventStoreConfigSchema()
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=AsyncMock(),
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=DecisionTranslator(),
        monitor=OrderMonitor(exchange=exchange, timeout_s=1),
        event_store=RedisEventStore(redis_client, config),
    )

    await engine.execute(decision_message)

    streams = {call.args[0] for call in redis_client.client.xadd.await_args_list}
    assert streams
    assert streams <= set(config.streams.values())


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
    """Timeout with an unreachable cancel/poll must stay flagged for reconciliation."""
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
    exchange.cancel_order = AsyncMock(side_effect=RuntimeError("exchange down"))
    exchange.get_order = AsyncMock(side_effect=RuntimeError("exchange down"))
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
    # The resting order must still be tracked so a late fill gets protected.
    state_manager.save_pending_entry.assert_called_once()


def _limit_order(
    *,
    status: OrderStatus,
    executed_qty: Decimal = Decimal(0),
) -> OrderResponseSchema:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return OrderResponseSchema(
        symbol="BTCUSDT",
        order_id=456,
        client_order_id="decision-1",
        transact_time=now,
        price=Decimal(100),
        orig_qty=Decimal(1),
        executed_qty=executed_qty,
        status=status,
        time_in_force=TimeInForce.GTC,
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        time=now,
    )


def _timeout_engine(
    exchange: AsyncMock,
    state_manager: AsyncMock,
) -> ExecutionEngine:
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
    monitor = MagicMock(spec=OrderMonitor)
    monitor.wait_for_completion = AsyncMock(return_value=None)
    return ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=DecisionTranslator(),
        monitor=monitor,
        event_store=None,
    )


class TestEntryTimeout:
    @pytest.mark.asyncio
    async def test_unfilled_entry_is_cancelled_on_timeout(
        self,
        decision_message,
    ) -> None:
        exchange = AsyncMock()
        exchange.create_order = AsyncMock(
            return_value=_limit_order(status=OrderStatus.NEW),
        )
        exchange.cancel_order = AsyncMock(
            return_value=_limit_order(status=OrderStatus.CANCELED),
        )
        state_manager = AsyncMock()
        engine = _timeout_engine(exchange, state_manager)

        result = await engine.execute(decision_message)

        exchange.cancel_order.assert_called_once_with(
            symbol="BTCUSDT",
            order_id=456,
        )
        assert result.status == "EXPIRED"
        assert result.needs_reconciliation is False
        state_manager.update_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_fill_racing_the_cancel_is_protected(
        self,
        decision_message,
    ) -> None:
        exchange = AsyncMock()
        exchange.create_order = AsyncMock(
            return_value=_limit_order(status=OrderStatus.NEW),
        )
        exchange.cancel_order = AsyncMock(side_effect=ExchangeError("gone", code=-2011))
        exchange.get_order = AsyncMock(
            return_value=_limit_order(
                status=OrderStatus.FILLED,
                executed_qty=Decimal(1),
            ),
        )
        state_manager = AsyncMock()
        engine = _timeout_engine(exchange, state_manager)

        result = await engine.execute(decision_message)

        assert result.status == "FILLED"
        state_manager.update_position.assert_called_once()
        sides = [c.kwargs["order_type"] for c in exchange.create_order.call_args_list]
        assert OrderType.STOP_MARKET in sides
        assert OrderType.TAKE_PROFIT_MARKET in sides

    @pytest.mark.asyncio
    async def test_partial_fill_is_protected_after_cancel(
        self,
        decision_message,
    ) -> None:
        exchange = AsyncMock()
        exchange.create_order = AsyncMock(
            return_value=_limit_order(status=OrderStatus.NEW),
        )
        exchange.cancel_order = AsyncMock(
            return_value=_limit_order(
                status=OrderStatus.CANCELED,
                executed_qty=Decimal("0.4"),
            ),
        )
        state_manager = AsyncMock()
        engine = _timeout_engine(exchange, state_manager)

        result = await engine.execute(decision_message)

        assert result.status == "FILLED"
        stored = state_manager.update_position.call_args.args[0]
        assert stored.quantity == Decimal("0.4")


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


def _order_response(order_type: OrderType, order_id: int) -> OrderResponseSchema:
    return OrderResponseSchema(
        symbol="BTCUSDT",
        order_id=order_id,
        client_order_id="c",
        transact_time=datetime(2026, 1, 1, tzinfo=UTC),
        price=Decimal(0),
        orig_qty=Decimal("0.1"),
        executed_qty=Decimal(0),
        status=OrderStatus.NEW,
        time_in_force=TimeInForce.GTC,
        type=order_type,
        side=OrderSide.SELL,
    )


@pytest.mark.asyncio
async def test_failed_take_profit_flags_position_for_retry() -> None:
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(
        side_effect=[
            _order_response(OrderType.STOP_MARKET, 1),
            RuntimeError("rate limited"),
        ],
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

    await engine._placer.place_initial(_sample_position())

    # SL stays live: no emergency close, only the two protective attempts.
    assert exchange.create_order.await_count == 2
    flagged = state_manager.update_position.await_args.args[0]
    assert flagged.needs_tp_retry is True


@pytest.mark.parametrize(
    ("code", "record_removed"),
    [(-2011, True), (-1007, False)],
)
@pytest.mark.asyncio
async def test_cancel_failure_keeps_order_record_unless_already_gone(
    code: int,
    record_removed: bool,
) -> None:
    exchange = AsyncMock()
    exchange.cancel_order = AsyncMock(side_effect=ExchangeError("x", code=code))
    state_manager = AsyncMock()
    state_manager.orders.get_by_position = AsyncMock(
        return_value=[
            OpenOrderSchema(
                order_id="42",
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                order_type=OrderType.STOP_MARKET,
                price=Decimal(49000),
                quantity=Decimal("0.1"),
                status=OrderStatus.NEW,
                linked_position_id="pos-1",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ],
    )
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=AsyncMock(),
        staleness_checker=MagicMock(),
        translator=DecisionTranslator(),
        monitor=MagicMock(spec=OrderMonitor),
        event_store=None,
    )

    await engine._linked_orders.cancel_for_position(_sample_position())

    assert state_manager.remove_order.await_count == int(record_removed)


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


def _engine_with_real_validator(
    decision_exchange: AsyncMock,
    balance: Decimal,
    **engine_kwargs,
) -> ExecutionEngine:
    account = AccountStateSchema(
        total_balance_usdt=balance,
        available_balance_usdt=balance,
        locked_balance_usdt=Decimal(0),
        peak_balance=balance,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    state_manager = AsyncMock()
    state_manager.get_account_state = AsyncMock(return_value=account)
    state_manager.get_current_drawdown = AsyncMock(return_value=Decimal(0))
    state_manager.get_all_positions = AsyncMock(return_value=[])
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    liquidation_calculator = MagicMock(spec=LiquidationCalculator)
    liquidation_calculator.estimate_liquidation_price = AsyncMock(
        return_value=Decimal(1),
    )
    return ExecutionEngine(
        exchange=decision_exchange,
        state_manager=state_manager,
        risk_validator=DynamicRiskValidator(
            liquidation_calculator=liquidation_calculator,
        ),
        staleness_checker=staleness_checker,
        translator=DecisionTranslator(),
        monitor=OrderMonitor(exchange=decision_exchange, timeout_s=1),
        event_store=None,
        **engine_kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("size_multiplier", "expected_qty"),
    [(Decimal(1), Decimal(2)), (Decimal("0.5"), Decimal(1))],
)
async def test_engine_applies_decision_size_multiplier(
    decision_message,
    filled_order_response,
    size_multiplier: Decimal,
    expected_qty: Decimal,
) -> None:
    """Balance 1000, 1% risk 10 / stop 5 = 2 units; filters can only shrink it."""
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(return_value=filled_order_response)
    engine = _engine_with_real_validator(exchange, Decimal(1000))
    decision = decision_message.model_copy(
        update={"size_multiplier": size_multiplier},
    )

    result = await engine.execute(decision)

    assert result.status == "FILLED"
    entry_order = exchange.create_order.call_args_list[0]
    assert entry_order.kwargs["quantity"] == expected_qty


@pytest.mark.asyncio
async def test_engine_rejects_when_filter_reduction_breaks_min_notional(
    decision_message,
) -> None:
    """Balance 150: 0.3 units ($30) x 0.25 = 0.075 units ($7.50) < $10 floor."""
    exchange = AsyncMock()
    engine = _engine_with_real_validator(exchange, Decimal(150))
    decision = decision_message.model_copy(
        update={"size_multiplier": Decimal("0.25")},
    )

    result = await engine.execute(decision)

    assert result.status == "REJECTED"
    assert result.error_message is not None
    assert "below minimum" in result.error_message
    exchange.create_order.assert_not_called()


@pytest.mark.asyncio
async def test_engine_validates_with_symbol_specific_leverage(
    decision_message,
) -> None:
    exchange = AsyncMock()
    risk_validator = AsyncMock()
    risk_validator.validate_trade = AsyncMock(
        return_value=RiskValidationResultSchema(
            is_valid=False,
            rejection_reasons=["stop here"],
            volatility_regime=VolatilityRegime.NORMAL,
            recommended_size=Decimal(0),
            size_multiplier=Decimal(1),
            warnings=[],
            should_close_all=False,
        ),
    )
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=AsyncMock(),
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=DecisionTranslator(),
        monitor=OrderMonitor(exchange=exchange, timeout_s=1),
        leverage=3,
        symbol_leverage={"BTCUSDT": 7},
    )

    await engine.execute(decision_message)

    assert risk_validator.validate_trade.call_args.kwargs["leverage"] == 7


@pytest.mark.asyncio
async def test_engine_continues_and_logs_when_event_store_fails(
    decision_message,
    filled_order_response,
    caplog: pytest.LogCaptureFixture,
) -> None:
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(return_value=filled_order_response)
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
    event_store = MagicMock()
    event_store.append = AsyncMock(side_effect=ConnectionError("redis down"))
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=AsyncMock(),
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=DecisionTranslator(),
        monitor=OrderMonitor(exchange=exchange, timeout_s=1),
        event_store=event_store,
    )

    result = await engine.execute(decision_message)

    assert result.status == "FILLED"
    assert event_store.append.await_count >= 2
    assert "was NOT recorded" in caplog.text
