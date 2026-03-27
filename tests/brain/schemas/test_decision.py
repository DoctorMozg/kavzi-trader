from decimal import Decimal

import pytest

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
