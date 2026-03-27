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


class TestAnalystDecisionSchemaValidator:
    def test_high_confluence_forces_setup_valid(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=False,
            direction="SHORT",
            confluence_score=8,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is True

    def test_low_confluence_keeps_setup_invalid(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=False,
            direction="SHORT",
            confluence_score=5,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is False

    def test_boundary_score_7_forces_valid(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=False,
            direction="LONG",
            confluence_score=7,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is True

    def test_boundary_score_6_keeps_original(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=True,
            direction="LONG",
            confluence_score=6,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is True

    def test_high_confluence_with_valid_true_unchanged(self) -> None:
        result = AnalystDecisionSchema(
            setup_valid=True,
            direction="LONG",
            confluence_score=9,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_make_reasoning(),
        )
        assert result.setup_valid is True
