from decimal import Decimal

import pytest
from pydantic import ValidationError

from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.trade_structure import TradeStructureSchema

_STUB_REASONING = (
    "EMA alignment is bullish with EMA20 above EMA50 above EMA200. "
    "RSI at 55 supports continuation. Volume confirms the breakout."
)


def _wait_decision(
    confidence: float = 0.3, reasoning: str = _STUB_REASONING
) -> TradeDecisionSchema:
    return TradeDecisionSchema(
        action="WAIT",
        confidence=confidence,
        reasoning=reasoning,
        entry_tactic=None,
        entry_level_index=None,
        stop_level_index=None,
        stop_atr_multiplier=None,
        target_style=None,
    )


def test_valid_long_with_atr_stop() -> None:
    decision = TradeDecisionSchema(
        action="LONG",
        confidence=0.8,
        reasoning=_STUB_REASONING,
        entry_tactic="IMMEDIATE",
        entry_level_index=None,
        stop_level_index=None,
        stop_atr_multiplier=Decimal("1.5"),
        target_style="ATR_2X",
    )
    assert decision.action == "LONG"
    assert decision.entry_tactic == "IMMEDIATE"
    assert decision.stop_atr_multiplier == Decimal("1.5")
    assert decision.stop_level_index is None
    assert decision.target_style == "ATR_2X"


def test_valid_short_with_level_stop() -> None:
    decision = TradeDecisionSchema(
        action="SHORT",
        confidence=0.7,
        reasoning=_STUB_REASONING,
        entry_tactic="IMMEDIATE",
        entry_level_index=None,
        stop_level_index=0,
        stop_atr_multiplier=None,
        target_style="STRUCTURAL",
    )
    assert decision.action == "SHORT"
    assert decision.stop_level_index == 0
    assert decision.stop_atr_multiplier is None
    assert decision.target_style == "STRUCTURAL"


def test_wait_allows_all_none_structure() -> None:
    decision = _wait_decision()
    assert decision.entry_tactic is None
    assert decision.entry_level_index is None
    assert decision.stop_level_index is None
    assert decision.stop_atr_multiplier is None
    assert decision.target_style is None


def test_long_without_target_style_raises() -> None:
    with pytest.raises(ValidationError, match="requires target_style"):
        TradeDecisionSchema(
            action="LONG",
            confidence=0.8,
            reasoning=_STUB_REASONING,
            entry_tactic="IMMEDIATE",
            entry_level_index=None,
            stop_level_index=None,
            stop_atr_multiplier=Decimal("1.5"),
            target_style=None,
        )


def test_long_with_both_stop_anchors_raises() -> None:
    with pytest.raises(ValidationError, match="exactly one stop anchor"):
        TradeDecisionSchema(
            action="LONG",
            confidence=0.8,
            reasoning=_STUB_REASONING,
            entry_tactic="IMMEDIATE",
            entry_level_index=None,
            stop_level_index=1,
            stop_atr_multiplier=Decimal("1.5"),
            target_style="ATR_2X",
        )


def test_long_without_stop_anchor_raises() -> None:
    with pytest.raises(ValidationError, match="exactly one stop anchor"):
        TradeDecisionSchema(
            action="LONG",
            confidence=0.8,
            reasoning=_STUB_REASONING,
            entry_tactic="IMMEDIATE",
            entry_level_index=None,
            stop_level_index=None,
            stop_atr_multiplier=None,
            target_style="ATR_2X",
        )


def test_pullback_without_entry_level_index_raises() -> None:
    with pytest.raises(ValidationError, match="requires entry_level_index"):
        TradeDecisionSchema(
            action="SHORT",
            confidence=0.7,
            reasoning=_STUB_REASONING,
            entry_tactic="PULLBACK_TO_LEVEL",
            entry_level_index=None,
            stop_level_index=0,
            stop_atr_multiplier=None,
            target_style="STRUCTURAL",
        )


def test_entry_tactic_defaults_to_immediate_for_long() -> None:
    """An LLM payload missing entry_tactic must not fail for LONG/SHORT."""
    payload = {
        "action": "LONG",
        "confidence": 0.8,
        "reasoning": _STUB_REASONING,
        "stop_atr_multiplier": "1.5",
        "target_style": "ATR_2X",
    }
    decision = TradeDecisionSchema.model_validate(payload)
    assert decision.entry_tactic == "IMMEDIATE"


def test_entry_tactic_not_defaulted_for_wait() -> None:
    payload = {
        "action": "WAIT",
        "confidence": 0.2,
        "reasoning": _STUB_REASONING,
    }
    decision = TradeDecisionSchema.model_validate(payload)
    assert decision.entry_tactic is None


def test_to_structure_round_trip_for_long() -> None:
    decision = TradeDecisionSchema(
        action="LONG",
        confidence=0.8,
        reasoning=_STUB_REASONING,
        entry_tactic="PULLBACK_TO_LEVEL",
        entry_level_index=2,
        stop_level_index=None,
        stop_atr_multiplier=Decimal("1.5"),
        target_style="ATR_3X",
    )
    structure = decision.to_structure()
    assert isinstance(structure, TradeStructureSchema)
    assert structure.direction == "LONG"
    assert structure.entry_tactic == "PULLBACK_TO_LEVEL"
    assert structure.entry_level_index == 2
    assert structure.stop_level_index is None
    assert structure.stop_atr_multiplier == Decimal("1.5")
    assert structure.target_style == "ATR_3X"


def test_to_structure_falls_back_to_immediate_for_explicit_none_tactic() -> None:
    """An explicit null entry_tactic survives validation but maps to IMMEDIATE."""
    decision = TradeDecisionSchema(
        action="LONG",
        confidence=0.8,
        reasoning=_STUB_REASONING,
        entry_tactic=None,
        entry_level_index=None,
        stop_level_index=None,
        stop_atr_multiplier=Decimal("1.0"),
        target_style="ATR_2X",
    )
    assert decision.entry_tactic is None
    assert decision.to_structure().entry_tactic == "IMMEDIATE"


def test_to_structure_raises_for_wait() -> None:
    decision = _wait_decision()
    with pytest.raises(ValueError, match="No trade structure"):
        decision.to_structure()


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_confidence_bounds_accepted(confidence: float) -> None:
    decision = _wait_decision(confidence=confidence)
    assert decision.confidence == confidence


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_out_of_bounds_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        _wait_decision(confidence=confidence)


@pytest.mark.parametrize("length", [40, 600])
def test_reasoning_length_bounds_accepted(length: int) -> None:
    decision = _wait_decision(reasoning="x" * length)
    assert len(decision.reasoning) == length


@pytest.mark.parametrize("length", [39, 601])
def test_reasoning_length_out_of_bounds_rejected(length: int) -> None:
    with pytest.raises(ValidationError):
        _wait_decision(reasoning="x" * length)
