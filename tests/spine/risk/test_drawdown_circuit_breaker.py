from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.spine.risk.drawdown_circuit_breaker import DrawdownCircuitBreaker
from kavzi_trader.spine.risk.trade_validation_params_schema import (
    TradeValidationParamsSchema,
)
from kavzi_trader.spine.risk.validator import DynamicRiskValidator

THRESHOLD = Decimal(10)


@pytest.fixture
def state() -> MagicMock:
    state = MagicMock()
    state.get_current_drawdown = AsyncMock(return_value=Decimal(0))
    return state


@pytest.fixture
def events() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def breaker(state: MagicMock, events: AsyncMock) -> DrawdownCircuitBreaker:
    return DrawdownCircuitBreaker(THRESHOLD, state, events)


async def test_below_threshold_does_nothing(
    breaker: DrawdownCircuitBreaker, state: MagicMock, events: AsyncMock
) -> None:
    state.get_current_drawdown.return_value = Decimal("9.99")

    assert await breaker.check(2) is False
    events.record.assert_not_awaited()


async def test_trips_at_threshold_and_emits_one_event(
    breaker: DrawdownCircuitBreaker, state: MagicMock, events: AsyncMock
) -> None:
    state.get_current_drawdown.return_value = THRESHOLD

    assert [await breaker.check(2), await breaker.check(2)] == [True, True]

    events.record.assert_awaited_once()
    kwargs = events.record.await_args.kwargs
    assert kwargs["event_type"] == "drawdown_close_all"
    assert kwargs["data"]["open_positions"] == 2


async def test_rearms_after_recovery(
    breaker: DrawdownCircuitBreaker, state: MagicMock, events: AsyncMock
) -> None:
    state.get_current_drawdown.return_value = Decimal(11)
    await breaker.check(1)
    state.get_current_drawdown.return_value = Decimal(1)
    await breaker.check(0)
    state.get_current_drawdown.return_value = Decimal(12)
    await breaker.check(1)

    assert events.record.await_count == 2


async def test_unreadable_drawdown_does_not_trip(
    breaker: DrawdownCircuitBreaker, state: MagicMock, events: AsyncMock
) -> None:
    state.get_current_drawdown.side_effect = RuntimeError("redis down")

    assert await breaker.check(1) is False
    events.record.assert_not_awaited()


async def test_new_entries_rejected_past_close_all_threshold(
    mock_state_manager: MagicMock,
) -> None:
    mock_state_manager.get_current_drawdown = AsyncMock(return_value=Decimal(11))
    validator = DynamicRiskValidator(RiskConfigSchema())

    result = await validator.validate_trade(
        TradeValidationParamsSchema.model_validate(
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "entry_price": Decimal(50000),
                "stop_loss": Decimal(49900),
                "take_profit": Decimal(50200),
                "current_atr": Decimal(100),
                "atr_history": [Decimal(100)] * 10,
            }
        ),
        mock_state_manager,
    )

    assert result.is_valid is False
    assert result.should_close_all is True
    assert any("close-all" in r for r in result.rejection_reasons)
