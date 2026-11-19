from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.candle_cache import COLUMNS, CandleCache
from kavzi_trader.evals.metrics_cache import MetricsCache
from kavzi_trader.evals.series_cache import TIME, VALUE, SeriesCache
from tests.cli.test_eval_trials_command import _invoke

BAR_MS = 4 * 3_600_000
FIRST_MS = 1_704_067_200_000  # 2024-01-01
BARS = 120 * 6
SYMBOLS = [f"C{i}USDT" for i in range(10)]


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """4h candles, 4-hourly ratios and 8-hourly funding for 10 coins and BTC."""
    rng = np.random.default_rng(8)
    open_ms = FIRST_MS + np.arange(BARS) * BAR_MS
    for symbol in [*SYMBOLS, "BTCUSDT"]:
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, BARS)))
        candles = pd.DataFrame(
            {
                "open_time_ms": open_ms,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "close_time_ms": open_ms + BAR_MS - 1,
                "quote_volume": 1.0,
                "trades_count": 1,
                "taker_buy_base_volume": 0.5,
                "taker_buy_quote_volume": 0.5,
            },
            columns=list(COLUMNS),
        )
        candles.to_csv(CandleCache(tmp_path, "4h").path(symbol), index=False)
        pd.DataFrame(
            {
                "time_ms": open_ms + BAR_MS - 1,
                "open_interest": 1.0,
                "global_ratio": np.exp(rng.normal(0, 0.3, BARS)),
                "top_position_ratio": 1.0,
            }
        ).to_csv(MetricsCache(tmp_path).path(symbol), index=False)
        settle = FIRST_MS + np.arange(BARS // 2) * 2 * BAR_MS
        pd.DataFrame({TIME: settle, VALUE: 0.0001}).to_csv(
            SeriesCache(tmp_path, "funding").path(symbol), index=False
        )
    return tmp_path


class TestCrowdingXsCommand:
    def test_reports_alpha_and_a_decision_and_registers_the_trial(
        self, config: AppConfig, cache_dir: Path
    ) -> None:
        out = config.system.results_dir / "xs.md"

        result = _invoke(
            config,
            "crowding-xs",
            "--cache-dir", str(cache_dir),
            "--symbols", ",".join(SYMBOLS),
            "--history", "30",
            "--from", "2024-02-15",
            "--to", "2024-04-20",
            "--out", str(out),
        )  # fmt: skip

        assert result.exception is None, result.output
        report = out.read_text(encoding="utf-8")
        assert "| Alpha vs BTCUSDT (annualised) |" in report
        assert "## Decision" in report
        assert ("PASS:" in report) != ("FAIL:" in report)
        assert "crowding-xs" in trials_path(config).read_text(encoding="utf-8")
