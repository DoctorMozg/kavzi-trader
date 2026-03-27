from kavzi_trader.brain.prompts.loader import PromptLoader


def test_prompt_loader_renders_system_prompt() -> None:
    loader = PromptLoader()
    rendered = loader.render_system_prompt("scout")
    assert "triage scanner" in rendered, "Expected scout system prompt."
    assert "INTERESTING" in rendered, "Expected INTERESTING verdict in scout prompt."
    assert "SKIP" in rendered, "Expected SKIP verdict in scout prompt."


def test_prompt_loader_renders_user_prompt() -> None:
    loader = PromptLoader()
    context = {
        "market_snapshot": {
            "symbol": "BTCUSDT",
            "current_price": "105",
            "timeframe": "15m",
            "volatility_regime": "NORMAL",
            "indicators": {
                "rsi_14": None,
                "ema_20": None,
                "ema_50": None,
                "ema_200": None,
                "sma_20": None,
                "atr_14": None,
                "volume": None,
                "macd": None,
                "bollinger": None,
            },
        },
    }
    rendered = loader.render_user_prompt("scout_scan", context)
    assert "BTCUSDT" in rendered, "Expected symbol in rendered prompt."
    assert "RSI=" in rendered, "Expected indicator values in rendered prompt."


def test_prompt_loader_renders_analyst_system_prompt() -> None:
    loader = PromptLoader()
    rendered = loader.render_system_prompt("analyst")
    assert "CONFLUENCE SCORING RUBRIC" in rendered, "Expected risk framework."
    assert "VOLATILITY REGIMES" in rendered, "Expected volatility guide."
    assert "ORDER FLOW INTERPRETATION" in rendered, "Expected order flow guide."


def test_prompt_loader_renders_trader_system_prompt() -> None:
    loader = PromptLoader()
    rendered = loader.render_system_prompt("trader")
    assert "POSITION MANAGEMENT PARAMETERS" in rendered, "Expected position mgmt guide."
    assert "ACCOUNT STATE RULES" in rendered, "Expected account state rules."
    assert "VOLATILITY REGIMES" in rendered, "Expected volatility guide."
