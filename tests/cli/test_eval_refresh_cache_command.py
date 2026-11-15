import time
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.config import AppConfig, TradingConfigSchema
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.series_cache import SeriesCache
from tests.cli.test_eval_run_command import _silenced_live_logs
from tests.evals.fake_exchange import FakeExchange

_DAY_MS = 86_400_000


@pytest.fixture
def config(app_config: AppConfig) -> AppConfig:
    trading = app_config.trading.model_copy(update={"symbols": ["BTCUSDT", "ETHUSDT"]})
    assert isinstance(trading, TradingConfigSchema)
    return app_config.model_copy(update={"trading": trading})


@pytest.fixture
def exchange() -> FakeExchange:
    return FakeExchange(int(time.time() * 1000))


def _refresh(
    config: AppConfig, exchange: FakeExchange, cache: Path, *args: str
) -> Result:
    with _silenced_live_logs():
        return CliRunner().invoke(
            eval_group,
            ["refresh-cache", "--cache-dir", str(cache), "--months", "0.1", *args],
            obj={"app_config": config, "exchange_client": exchange},
            standalone_mode=False,
        )


class TestRefreshCache:
    def test_fills_candles_funding_and_oi_up_to_today(
        self, config: AppConfig, exchange: FakeExchange, tmp_path: Path
    ) -> None:
        result = _refresh(config, exchange, tmp_path)

        assert result.exception is None
        today_ms = int(time.time() * 1000) // _DAY_MS * _DAY_MS
        for symbol in ("BTCUSDT", "ETHUSDT"):
            candles = CandleCache(tmp_path, "15m").load(symbol)
            assert int(candles["open_time_ms"].iloc[-1]) == today_ms - 15 * 60_000
            assert not SeriesCache(tmp_path, "funding").load(symbol).empty
            assert not SeriesCache(tmp_path, "oi_15m").load(symbol).empty
        lines = result.output.splitlines()
        assert [line.split(":")[0] for line in lines] == ["BTCUSDT", "ETHUSDT"]
        assert "15m candles" in lines[0]
        assert "OI 15m" in lines[0]

    def test_rerun_fetches_no_candles(
        self, config: AppConfig, exchange: FakeExchange, tmp_path: Path
    ) -> None:
        _refresh(config, exchange, tmp_path)
        exchange.kline_calls.clear()

        result = _refresh(config, exchange, tmp_path)

        assert result.exception is None
        assert exchange.kline_calls == []

    def test_other_interval_gets_its_own_cache(
        self, config: AppConfig, exchange: FakeExchange, tmp_path: Path
    ) -> None:
        result = _refresh(config, exchange, tmp_path, "--interval", "4h")

        assert result.exception is None
        assert {call[0] for call in exchange.kline_calls} == {"4h"}
        assert CandleCache(tmp_path, "4h").path("BTCUSDT").exists()
        assert not CandleCache(tmp_path, "15m").path("BTCUSDT").exists()
        # openInterestHist has no period above 30m.
        assert "OI 30m" in result.output
