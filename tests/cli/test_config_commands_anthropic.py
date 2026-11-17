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
