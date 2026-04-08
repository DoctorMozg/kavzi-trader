from kavzi_trader.brain.context.context_dicts import SystemPromptContextDict
from kavzi_trader.brain.prompts.loader import PromptLoader


def _make_system_prompt_context() -> SystemPromptContextDict:
    """Build a complete system prompt context for template rendering tests."""
    return SystemPromptContextDict(
        min_rr_ratio="2.0",
        drawdown_pause_percent="3.0",
        drawdown_close_all_percent="5.0",
        confluence_enter_min=6,
        volatility_low_threshold="-1.5",
        volatility_high_threshold="1.0",
        volatility_extreme_threshold="2.0",
        tier_1_min_confidence="0.65",
        tier_2_min_confidence="0.70",
        tier_3_min_confidence="0.85",
    )


def test_prompt_loader_renders_analyst_system_prompt() -> None:
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("analyst", context=context)
    assert "CONFLUENCE SCORING RUBRIC" in rendered, "Expected risk framework."
    assert "VOLATILITY REGIMES" in rendered, "Expected volatility guide."
    assert "ORDER FLOW INTERPRETATION" in rendered, "Expected order flow guide."


def test_prompt_loader_renders_trader_system_prompt() -> None:
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("trader", context=context)
    assert "FUNDING COSTS" in rendered, "Expected funding costs guidance."
    assert "ACCOUNT STATE RULES" in rendered, "Expected account state rules."
    assert "VOLATILITY REGIMES" in rendered, "Expected volatility guide."
