from collections.abc import Callable

import pytest
from click.testing import CliRunner, Result
from pydantic import SecretStr

from kavzi_trader.cli.commands.config import config_command
from kavzi_trader.config import AppConfig

_BINANCE_KEY = "binance-key-VALUE-1"
_BINANCE_SECRET = "binance-secret-VALUE-2"  # noqa: S105 - fake test value
_OPENROUTER_KEY = "openrouter-key-VALUE-3"


@pytest.fixture
def make_config() -> Callable[..., AppConfig]:
    def _make(
        binance_key: str = _BINANCE_KEY,
        openrouter_key: str = _OPENROUTER_KEY,
    ) -> AppConfig:
        base = AppConfig.from_env()
        return base.model_copy(
            update={
                "api": base.api.model_copy(
                    update={
                        "binance": base.api.binance.model_copy(
                            update={
                                "api_key": SecretStr(binance_key),
                                "api_secret": SecretStr(_BINANCE_SECRET),
                            },
                        ),
                    },
                ),
                "brain": base.brain.model_copy(
                    update={"openrouter_api_key": SecretStr(openrouter_key)},
                ),
            },
        )

    return _make


def _run(config: AppConfig, *args: str) -> Result:
    return CliRunner().invoke(
        config_command,
        ["--validate", *args],
        obj={"app_config": config},
    )


def test_validate_output_contains_no_secret_values(
    make_config: Callable[..., AppConfig],
) -> None:
    result = _run(make_config())

    assert result.exit_code == 0
    for secret in (_BINANCE_KEY, _BINANCE_SECRET, _OPENROUTER_KEY):
        assert secret not in result.output
    assert "valid" in result.output.lower()


def test_validate_fails_when_live_secrets_missing(
    make_config: Callable[..., AppConfig],
) -> None:
    result = _run(make_config(binance_key=""))

    assert result.exit_code != 0
    assert "KT_BINANCE_API_KEY" in result.output


def test_validate_paper_does_not_need_binance_keys(
    make_config: Callable[..., AppConfig],
) -> None:
    result = _run(make_config(binance_key=""), "--paper")

    assert result.exit_code == 0


@pytest.mark.parametrize("mode_args", [(), ("--paper",)])
def test_validate_fails_without_openrouter_key(
    make_config: Callable[..., AppConfig],
    mode_args: tuple[str, ...],
) -> None:
    result = _run(make_config(openrouter_key=""), *mode_args)

    assert result.exit_code != 0
    assert "KT_OPENROUTER_API_KEY" in result.output
