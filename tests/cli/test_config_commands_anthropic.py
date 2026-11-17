from collections.abc import Callable

import pytest
from click.testing import CliRunner, Result
from pydantic import SecretStr

from kavzi_trader.brain.config import AgentModelConfigSchema
from kavzi_trader.cli.commands.config import config_command
from kavzi_trader.commons.llm_provider import LlmProvider
from kavzi_trader.config import AppConfig

_ANTHROPIC_KEY = "anthropic-key-VALUE-9"


@pytest.fixture
def make_config(llm_app_config: AppConfig) -> Callable[[str], AppConfig]:
    def _make(anthropic_key: str) -> AppConfig:
        base = llm_app_config
        brain = base.brain.model_copy(
            update={
                "openrouter_api_key": SecretStr("openrouter-key"),
                "anthropic_api_key": SecretStr(anthropic_key),
                "trader": AgentModelConfigSchema(provider=LlmProvider.ANTHROPIC),
            },
        )
        return base.model_copy(update={"brain": brain})

    return _make


def _run(config: AppConfig) -> Result:
    return CliRunner().invoke(
        config_command,
        ["--validate", "--paper"],
        obj={"app_config": config},
        standalone_mode=False,
    )


def test_validate_masks_anthropic_key(make_config: Callable[[str], AppConfig]) -> None:
    result = _run(make_config(_ANTHROPIC_KEY))

    assert result.exit_code == 0
    assert _ANTHROPIC_KEY not in result.output
    assert "Anthropic API key: set" in result.output


def test_validate_fails_clearly_without_anthropic_key(
    make_config: Callable[[str], AppConfig],
) -> None:
    result = _run(make_config(""))

    assert result.exit_code != 0
    assert "KT_ANTHROPIC_API_KEY" in str(result.exception)


def _trend_config(app_config: AppConfig, *, gate_enabled: bool) -> AppConfig:
    trend = app_config.strategy.trend_following
    gate = trend.gate.model_copy(update={"enabled": gate_enabled})
    strategy = app_config.strategy.model_copy(
        update={
            "active": "trend_following",
            "trend_following": trend.model_copy(update={"gate": gate}),
        }
    )
    brain = app_config.brain.model_copy(update={"anthropic_api_key": SecretStr("")})
    return app_config.model_copy(update={"strategy": strategy, "brain": brain})


def test_trend_with_shadow_gate_needs_the_anthropic_key(app_config: AppConfig) -> None:
    result = _run(_trend_config(app_config, gate_enabled=True))

    assert result.exit_code != 0
    assert "KT_ANTHROPIC_API_KEY" in str(result.exception)


def test_trend_without_gate_needs_no_llm_key(app_config: AppConfig) -> None:
    result = _run(_trend_config(app_config, gate_enabled=False))

    assert result.exit_code == 0
