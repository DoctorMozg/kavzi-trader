from decimal import Decimal

import pytest
from pydantic import ValidationError

from kavzi_trader.brain.schemas.decision import TradeDecisionSchema

_STUB_REASONING = (
    "EMA alignment is bullish with EMA20 above EMA50 above EMA200. "
    "RSI at 55 supports continuation. Volume confirms the breakout."
)


def test_trade_decision_valid_buy() -> None:
    decision = TradeDecisionSchema(
        action="LONG",
        confidence=0.8,
        reasoning=_STUB_REASONING,
        suggested_entry=Decimal(100),
        suggested_stop_loss=Decimal(95),
        suggested_take_profit=Decimal(110),
    )
    assert decision.action == "LONG", "Expected BUY action."


def test_trade_decision_requires_prices_for_trade() -> None:
    with pytest.raises(ValueError, match="Trade requires entry"):
        TradeDecisionSchema(
            action="LONG",
            confidence=0.8,
            reasoning=_STUB_REASONING,
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
        )


def test_trade_decision_enforces_rr_ratio() -> None:
    with pytest.raises(ValueError, match="Risk/reward ratio below minimum"):
        TradeDecisionSchema(
            action="LONG",
            confidence=0.8,
            reasoning=_STUB_REASONING,
            suggested_entry=Decimal(100),
            suggested_stop_loss=Decimal(99),
            suggested_take_profit=Decimal("100.5"),
        )


def test_reasoning_minimum_40() -> None:
    """Reasoning of exactly 40 chars must be accepted."""
    reasoning_40 = "x" * 40
    decision = TradeDecisionSchema(
        action="WAIT",
        confidence=0.3,
        reasoning=reasoning_40,
        suggested_entry=None,
        suggested_stop_loss=None,
        suggested_take_profit=None,
    )
    assert len(decision.reasoning) == 40


def test_reasoning_boundary_40_rejects_39() -> None:
    """Reasoning of 39 chars must be rejected — boundary is exactly 40."""
    reasoning_39 = "x" * 39
    with pytest.raises(ValidationError):
        TradeDecisionSchema(
            action="WAIT",
            confidence=0.3,
            reasoning=reasoning_39,
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
        )
