from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelsSchema,
)


def _make_reasoning() -> str:
    return (
        "Trend is bearish with EMA20 < EMA50 < EMA200. "
        "RSI at 35 supports downside. Volume ratio 1.3 confirms selling pressure. "
        "Bollinger lower band breached. Order flow neutral."
    )


class TestAnalystDecisionSchema:
    """The schema no longer mutates setup_valid based on confluence_score.

    setup_valid is the LLM's own boolean output. confluence_score is an
    independent 0-11 signal. The hysteresis gate lives in AgentRouter, not
    in the schema, so the two fields must round-trip unchanged.
    """

    def test_high_confluence_with_false_setup_valid_preserved(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=False,
            direction="SHORT",
            confluence_score=8,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is False
        assert result.confluence_score == 8

    def test_low_confluence_keeps_setup_invalid(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=False,
            direction="SHORT",
            confluence_score=5,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is False

    def test_mid_confluence_with_true_setup_valid_preserved(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=True,
            direction="LONG",
            confluence_score=6,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is True
        assert result.confluence_score == 6

    def test_high_confluence_with_valid_true_unchanged(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=True,
            direction="LONG",
            confluence_score=9,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is True

    def test_zero_confluence_with_false_setup_valid(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=False,
            direction="NEUTRAL",
            confluence_score=0,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is False
        assert result.confluence_score == 0
