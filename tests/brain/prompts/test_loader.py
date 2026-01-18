from kavzi_trader.brain.prompts.loader import PromptLoader


def test_prompt_loader_renders_system_prompt() -> None:
    loader = PromptLoader()
    rendered = loader.render_system_prompt("scout")
    assert "fast market scanner" in rendered, "Expected scout system prompt."


def test_prompt_loader_renders_user_prompt() -> None:
    loader = PromptLoader()
    context = {"market_snapshot_json": '{"symbol":"BTCUSDT"}'}
    rendered = loader.render_user_prompt("scout_scan", context)
    assert "Market snapshot" in rendered, "Expected market snapshot context."
