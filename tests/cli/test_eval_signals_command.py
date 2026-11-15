from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.cli.commands import evals as evals_cli
from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.config import AppConfig, TradingConfigSchema
from tests.cli.test_eval_run_command import _silenced_live_logs
from tests.evals.eval_fixtures import btc_frame, write_cache
from tests.evals.fake_exchange import FakeExchange
from tests.evals.frames import BASE_MS


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
    assert "No cached 15m candles in" in str(result.exception)


def test_funding_flag_downloads_and_scores_funding(
    config: AppConfig, tmp_path: Path
) -> None:
    write_cache(tmp_path / "cache", btc_frame(extra_bars=200))
    out = tmp_path / "signals.md"
    client = FakeExchange(BASE_MS)

    with _silenced_live_logs():
        result = CliRunner().invoke(
            eval_group,
            ["signals", "--cache-dir", str(tmp_path / "cache"), "--funding",
             "--stride", "29", "--bracket", "1:2:10", "--out", str(out)],
            obj={"app_config": config, "exchange_client": client},
            standalone_mode=False,
        )  # fmt: skip

    assert result.exception is None
    assert client.funding_calls
    assert (tmp_path / "cache" / "BTCUSDT_funding.csv.gz").exists()
    assert "| LONG | funding_favorable |" in out.read_text(encoding="utf-8")


def test_oi_flag_scores_oi_signals_in_the_oi_window(
    config: AppConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = btc_frame(extra_bars=400)
    write_cache(tmp_path / "cache", frame)
    out = tmp_path / "signals.md"
    # Synthetic candles are years old; let the OI window reach back to them.
    monkeypatch.setattr(evals_cli, "_OI_LOOKBACK_MS", 10**13)
    client = FakeExchange(int(frame["close_time_ms"].iloc[-1]))

    with _silenced_live_logs():
        result = CliRunner().invoke(
            eval_group,
            ["signals", "--cache-dir", str(tmp_path / "cache"), "--oi",
             "--stride", "29", "--bracket", "1:2:10", "--out", str(out)],
            obj={"app_config": config, "exchange_client": client},
            standalone_mode=False,
        )  # fmt: skip

    assert result.exception is None
    assert client.oi_calls
    assert client.funding_calls
    text = out.read_text(encoding="utf-8")
    assert "| LONG | oi_supports_direction |" in text
    assert "| SHORT | oi_funding_divergence |" in text
    assert "| LONG | funding_favorable |" in text


def test_candidates_flag_adds_candidate_signals(
    config: AppConfig, tmp_path: Path
) -> None:
    write_cache(tmp_path / "cache", btc_frame(extra_bars=200))
    out = tmp_path / "signals.md"

    result = _invoke(
        config, tmp_path / "cache",
        "--candidates", "--stride", "29", "--bracket", "1:2:10", "--out", str(out),
    )  # fmt: skip

    assert result.exception is None
    text = out.read_text(encoding="utf-8")
    for name in ("taker_flow", "htf_trend", "btc_lead"):
        assert f"| LONG | {name} |" in text


class TestInterval:
    def test_reads_the_cache_of_the_given_interval(
        self, config: AppConfig, tmp_path: Path
    ) -> None:
        write_cache(tmp_path / "cache", btc_frame(extra_bars=200), interval="4h")
        out = tmp_path / "signals.md"

        result = _invoke(
            config, tmp_path / "cache",
            "--interval", "4h", "--stride", "29", "--bracket", "1:2:10",
            "--out", str(out),
        )  # fmt: skip

        assert result.exception is None
        assert "Every 29th 4h bar of BTCUSDT;" in out.read_text(encoding="utf-8")

    def test_missing_interval_cache_points_at_refresh(
        self, config: AppConfig, tmp_path: Path
    ) -> None:
        write_cache(tmp_path / "cache", btc_frame())
        result = _invoke(config, tmp_path / "cache", "--interval", "1h")
        assert result.exception is not None
        assert "eval refresh-cache --interval 1h" in str(result.exception)
