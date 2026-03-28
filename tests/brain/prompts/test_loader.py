from kavzi_trader.brain.prompts.loader import PromptLoader


def test_prompt_loader_renders_analyst_system_prompt() -> None:
    loader = PromptLoader()
    rendered = loader.render_system_prompt("analyst")
    assert "CONFLUENCE SCORING RUBRIC" in rendered, "Expected risk framework."
    assert "VOLATILITY REGIMES" in rendered, "Expected volatility guide."
    assert "ORDER FLOW INTERPRETATION" in rendered, "Expected order flow guide."


def test_prompt_loader_renders_trader_system_prompt() -> None:
    loader = PromptLoader()
    rendered = loader.render_system_prompt("trader")
    assert "FUNDING COSTS" in rendered, "Expected funding costs guidance."
    assert "ACCOUNT STATE RULES" in rendered, "Expected account state rules."
    assert "VOLATILITY REGIMES" in rendered, "Expected volatility guide."
