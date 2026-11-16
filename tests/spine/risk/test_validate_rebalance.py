from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.spine.risk.rebalance_validation_params_schema import (
    RebalanceValidationParamsSchema,
)
from kavzi_trader.spine.risk.validator import DynamicRiskValidator

_NOW_MS = 1_000_000


def _params(**overrides: object) -> RebalanceValidationParamsSchema:
    base: dict[str, object] = {
        "symbol": "BTCUSDT",
        "mark_price": Decimal(100),
        "current_qty": Decimal(0),
        "target_qty": Decimal(10),
        "equity": Decimal(10000),
        "leverage": 1,
        "disaster_stop_price": Decimal(70),
        "expires_at_ms": _NOW_MS + 60_000,
        "now_ms": _NOW_MS,
    }
    return RebalanceValidationParamsSchema.model_validate(base | overrides)


@pytest.fixture
def validator() -> DynamicRiskValidator:
    return DynamicRiskValidator(RiskConfigSchema())


async def test_accepts_clean_open(
    validator: DynamicRiskValidator, mock_state_manager: MagicMock
) -> None:
    assert await validator.validate_rebalance(_params(), mock_state_manager) == []


async def test_rejects_open_while_paused_by_drawdown(
    validator: DynamicRiskValidator, mock_state_manager: MagicMock
) -> None:
    mock_state_manager.get_current_drawdown = AsyncMock(return_value=Decimal(4))

    reasons = await validator.validate_rebalance(_params(), mock_state_manager)

    assert any("pause threshold" in reason for reason in reasons)


async def test_rejects_expired_intent(
    validator: DynamicRiskValidator, mock_state_manager: MagicMock
) -> None:
    reasons = await validator.validate_rebalance(
        _params(expires_at_ms=_NOW_MS - 1), mock_state_manager
    )

    assert any("expired" in reason for reason in reasons)


async def test_rejects_resize_breaching_notional_cap(
    validator: DynamicRiskValidator, mock_state_manager: MagicMock
) -> None:
    # Cap is 50% of 10000 = 5000; growing 40 -> 60 units is 6000 notional.
    reasons = await validator.validate_rebalance(
        _params(current_qty=Decimal(40), target_qty=Decimal(60)), mock_state_manager
    )

    assert any("exceeds cap" in reason for reason in reasons)


async def test_rejects_grow_when_margin_ratio_is_too_high(
    validator: DynamicRiskValidator, mock_state_manager: MagicMock
) -> None:
    account = mock_state_manager.get_account_state.return_value
    mock_state_manager.get_account_state = AsyncMock(
        return_value=account.model_copy(update={"margin_ratio": Decimal("0.9")}),
    )

    reasons = await validator.validate_rebalance(_params(), mock_state_manager)

    assert any("margin ratio" in reason for reason in reasons)


async def test_rejects_when_disaster_stop_sits_past_liquidation(
    mock_state_manager: MagicMock,
) -> None:
    calculator = MagicMock()
    calculator.estimate_liquidation_price = AsyncMock(return_value=Decimal(80))
    validator = DynamicRiskValidator(
        RiskConfigSchema(), liquidation_calculator=calculator
    )

    reasons = await validator.validate_rebalance(
        _params(leverage=5), mock_state_manager
    )

    assert any("liquidation" in reason for reason in reasons)


async def test_reductions_pass_while_paused_and_over_cap(
    validator: DynamicRiskValidator, mock_state_manager: MagicMock
) -> None:
    mock_state_manager.get_current_drawdown = AsyncMock(return_value=Decimal(9))

    reasons = await validator.validate_rebalance(
        _params(current_qty=Decimal(80), target_qty=Decimal(60)), mock_state_manager
    )

    assert reasons == []


async def test_expired_reduction_is_still_rejected(
    validator: DynamicRiskValidator, mock_state_manager: MagicMock
) -> None:
    reasons = await validator.validate_rebalance(
        _params(current_qty=Decimal(5), target_qty=Decimal(0), expires_at_ms=1),
        mock_state_manager,
    )

    assert len(reasons) == 1


async def test_resize_of_existing_position_ignores_max_positions(
    mock_state_manager: MagicMock,
) -> None:
    validator = DynamicRiskValidator(RiskConfigSchema(max_positions=1))
    mock_state_manager.get_all_positions = AsyncMock(return_value=[MagicMock()] * 8)

    reasons = await validator.validate_rebalance(
        _params(current_qty=Decimal(1), target_qty=Decimal(2)), mock_state_manager
    )

    assert reasons == []
