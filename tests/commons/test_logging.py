import logging
from pathlib import Path

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


class TestConsoleLevel:
    def test_debug_reaches_the_file_but_not_the_console(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        name = "kavzi_trader.test_console_level"
        logger = setup_logging(
            log_level="DEBUG", name=name, log_dir=tmp_path, console_level="INFO"
        )

        logger.debug("only in the file")
        logger.info("in both")
        for handler in logger.handlers:
            handler.flush()

        printed = capsys.readouterr().out
        assert "in both" in printed
        assert "only in the file" not in printed
        written = "".join(p.read_text() for p in tmp_path.iterdir())
        assert "only in the file" in written
        assert "in both" in written

    def test_console_follows_log_level_by_default(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        logger = setup_logging(log_level="DEBUG", name="kavzi_trader.test_default")
        logger.debug("shown")
        assert "shown" in capsys.readouterr().out
