import logging

import pytest

from kavzi_trader.commons.logging import setup_logging

_SECRET_VALUE = "super-secret-value-123"  # noqa: S105 - fake test value


@pytest.mark.parametrize(
    "env_name",
    ["BINANCE_TESTNET_API_SECRET", "APP_TOKEN", "DB_PASSWORD", "LOG_KEY"],
)
def test_setup_logging_does_not_log_env_secrets(
    env_name: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(env_name, _SECRET_VALUE)
    name = "kavzi_trader.test_secret_logging"

    with caplog.at_level(logging.DEBUG):
        setup_logging(name=name, console=False)

    assert _SECRET_VALUE not in caplog.text
