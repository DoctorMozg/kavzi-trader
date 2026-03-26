from decimal import Decimal

import pytest

from kavzi_trader.brain.schemas.decision import TradeDecisionSchema


def test_trade_decision_valid_buy() -> None:
    decision = TradeDecisionSchema(
        action="BUY",
        confidence=0.8,
        reasoning="Clear breakout with strong volume.",
        suggested_entry=Decimal(100),
        suggested_stop_loss=Decimal(95),
        suggested_take_profit=Decimal(110),
        position_management=None,
        calibrated_confidence=None,
    )
    assert decision.action == "BUY", "Expected BUY action."


def test_trade_decision_requires_prices_for_trade() -> None:
    with pytest.raises(ValueError, match="Trade requires entry"):
        TradeDecisionSchema(
            action="BUY",
            confidence=0.8,
            reasoning="Missing prices.",
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
            position_management=None,
            calibrated_confidence=None,
        )


def test_trade_decision_enforces_rr_ratio() -> None:
    with pytest.raises(ValueError, match="Risk/reward ratio below minimum"):
        TradeDecisionSchema(
            action="BUY",
            confidence=0.8,
            reasoning="Low reward.",
            suggested_entry=Decimal(100),
            suggested_stop_loss=Decimal(99),
            suggested_take_profit=Decimal("100.5"),
            position_management=None,
            calibrated_confidence=None,
        )
