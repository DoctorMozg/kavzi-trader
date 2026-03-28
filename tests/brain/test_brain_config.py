from kavzi_trader.brain.config import AgentModelConfigSchema, BrainConfigSchema


def test_brain_config_defaults() -> None:
    config = BrainConfigSchema()
    assert config.openrouter_api_key == ""
    assert config.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert config.analyst.model_id == "openai/gpt-5"
    assert config.trader.model_id == "anthropic/claude-opus-4.6"


def test_brain_config_custom_models() -> None:
    config = BrainConfigSchema(
        openrouter_api_key="test-key",
        analyst=AgentModelConfigSchema(model_id="google/gemini-pro-1.5"),
        trader=AgentModelConfigSchema(
            model_id="anthropic/claude-3-opus",
            retries=3,
            temperature=0.5,
        ),
    )
    assert config.openrouter_api_key == "test-key"
    assert config.analyst.model_id == "google/gemini-pro-1.5"
    assert config.trader.retries == 3
    assert config.trader.temperature == 0.5


def test_agent_model_config_defaults() -> None:
    config = AgentModelConfigSchema(model_id="test/model")
    assert config.retries == 1
    assert config.temperature == 0.0


def test_brain_config_frozen() -> None:
    config = BrainConfigSchema()
    try:
        config.openrouter_api_key = "new-key"  # type: ignore[misc]
    except Exception:
        pass
    else:
        msg = "BrainConfigSchema should be frozen"
        raise AssertionError(msg)
