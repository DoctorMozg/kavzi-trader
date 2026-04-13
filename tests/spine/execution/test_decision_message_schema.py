from decimal import Decimal

import pytest
from pydantic import ValidationError

from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


def _base_kwargs() -> dict:
    return {
        "decision_id": "decision-1",
        "symbol": "BTCUSDT",
        "entry_price": Decimal(100),
        "stop_loss": Decimal(95),
        "take_profit": Decimal(110),
        "raw_confidence": 0.8,
        "calibrated_confidence": 0.7,
        "volatility_regime": VolatilityRegime.NORMAL,
        "position_management": PositionManagementConfigSchema(),
        "created_at_ms": 1_000,
        "expires_at_ms": 60_000,
        "current_atr": Decimal(2),
    }


def test_valid_long_decision_passes_validator() -> None:
    decision = DecisionMessageSchema(action="LONG", **_base_kwargs())
    assert decision.action == "LONG"


def test_long_with_inverted_geometry_rejected() -> None:
    kwargs = _base_kwargs()
    kwargs["stop_loss"] = Decimal(110)
    kwargs["take_profit"] = Decimal(95)
    with pytest.raises(ValidationError):
        DecisionMessageSchema(action="LONG", **kwargs)


def test_short_geometry_requires_inverted_ordering() -> None:
    kwargs = _base_kwargs()
    kwargs["entry_price"] = Decimal(100)
    kwargs["stop_loss"] = Decimal(105)
    kwargs["take_profit"] = Decimal(90)
    decision = DecisionMessageSchema(action="SHORT", **kwargs)
    assert decision.action == "SHORT"


def test_insufficient_risk_reward_rejected() -> None:
    # R/R = 1 < MIN_RR_RATIO (2.0) should fail even with correct ordering.
    kwargs = _base_kwargs()
    kwargs["entry_price"] = Decimal(100)
    kwargs["stop_loss"] = Decimal(95)
    kwargs["take_profit"] = Decimal(105)
    with pytest.raises(ValidationError):
        DecisionMessageSchema(action="LONG", **kwargs)


def test_zero_quantity_rejected_when_set() -> None:
    kwargs = _base_kwargs()
    kwargs["quantity"] = Decimal(0)
    with pytest.raises(ValidationError):
        DecisionMessageSchema(action="LONG", **kwargs)


def test_none_quantity_allowed() -> None:
    # Risk validator computes the real size downstream; schema must not
    # require a pre-computed quantity. Translator is the final gate.
    decision = DecisionMessageSchema(action="LONG", quantity=None, **_base_kwargs())
    assert decision.quantity is None


def test_close_action_skips_geometry_validation() -> None:
    # CLOSE decisions don't carry real entry/stop/tp geometry.
    kwargs = _base_kwargs()
    kwargs["stop_loss"] = Decimal(100)
    kwargs["take_profit"] = Decimal(100)
    decision = DecisionMessageSchema(action="CLOSE", **kwargs)
    assert decision.action == "CLOSE"
