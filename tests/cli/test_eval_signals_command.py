from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.config import AppConfig, TradingConfigSchema
from tests.cli.test_eval_run_command import _silenced_live_logs
from tests.evals.eval_fixtures import btc_frame, write_cache


@pytest.fixture
def config(app_config: AppConfig) -> AppConfig:
    trading = app_config.trading.model_copy(update={"symbols": ["BTCUSDT", "ETHUSDT"]})
    assert isinstance(trading, TradingConfigSchema)
    return app_config.model_copy(update={"trading": trading})


def _invoke(config: AppConfig, cache: Path, *args: str) -> Result:
    with _silenced_live_logs():
        return CliRunner().invoke(
            eval_group,
            ["signals", "--cache-dir", str(cache), *args],
            obj={"app_config": config},
            standalone_mode=False,
        )


def test_writes_one_section_per_bracket(config: AppConfig, tmp_path: Path) -> None:
    write_cache(tmp_path / "cache", btc_frame(extra_bars=200))
    out = tmp_path / "signals.md"

    result = _invoke(
        config,
        tmp_path / "cache",
        "--stride", "29",
        "--bracket", "1.5:3:20",
        "--bracket", "1:2:10",
        "--out", str(out),
    )  # fmt: skip

    assert result.exception is None
    text = out.read_text(encoding="utf-8")
    assert "## 1.5/3 ATR, 20 bars" in text
    assert "## 1/2 ATR, 10 bars" in text
    # ETHUSDT has no cache, so only BTCUSDT is sampled.
    assert "Every 29th 15m bar of BTCUSDT;" in text
    assert result.output.splitlines()[0].startswith("1.5/3 ATR, 20 bars: ")
    assert f"Report: {out}" in result.output


def test_rejects_a_malformed_bracket(config: AppConfig, tmp_path: Path) -> None:
    write_cache(tmp_path / "cache", btc_frame())
    result = _invoke(config, tmp_path / "cache", "--bracket", "1.5:3")
    assert result.exception is not None
    assert "SL:TP:BARS" in str(result.exception)


def test_fails_without_cached_candles(config: AppConfig, tmp_path: Path) -> None:
    result = _invoke(config, tmp_path / "empty")
    assert result.exception is not None
    assert "No cached candles" in str(result.exception)
