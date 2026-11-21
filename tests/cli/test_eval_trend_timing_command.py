from pathlib import Path

import pandas as pd
import pytest

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.archive_series import ArchiveSeries
from tests.cli.test_eval_trials_command import WINDOW, _invoke

SYMBOLS = ["--symbols", "BTCUSDT,ETHUSDT"]
LABELS = ["A-12h", "A-6h", "A-4h", "B-12h", "B-6h", "B-4h"]


@pytest.fixture
def hourly_archive(archive: Path) -> Path:
    """The synthetic archive plus its 1h klines rolled up from the 1m ones."""
    series = ArchiveSeries(archive)
    store = ArchiveStore(archive)
    for symbol in ("BTCUSDT", "ETHUSDT"):
        bars = series.candles(symbol, "1h")
        months = pd.to_datetime(bars["open_time_ms"], unit="ms").dt.strftime("%Y-%m")
        for month, rows in bars.groupby(months):
            store.write(
                ARCHIVE_DATASETS["klines_1h"],
                symbol,
                str(month),
                rows.reset_index(drop=True),
            )
    return archive


class TestTrendTimingCommand:
    def test_scores_six_arms_against_the_base_and_registers_each_once(
        self, config: AppConfig, hourly_archive: Path
    ) -> None:
        out = config.system.results_dir / "timing.md"
        args = ["trend-timing", "--universe", "trading", "--archive-dir"]
        args += [str(hourly_archive), *SYMBOLS, *WINDOW, "--out", str(out)]

        first = _invoke(config, *args)
        again = _invoke(config, *args)

        assert first.exception is None, first.output
        report = out.read_text(encoding="utf-8")
        assert all(f"| {label} |" in report for label in LABELS)
        assert "Vol-spike halving is excluded from every arm" in report
        assert "Adjusted interval" in report
        # Two synthetic symbols cannot reproduce the real base Sharpe.
        assert "Reproduction: VOID" in report
        assert first.output.count("Trial registered") == 6
        assert "Trial registered" not in again.output
        assert len(trials_path(config).read_text(encoding="utf-8").splitlines()) == 6

    def test_missing_hourly_klines_name_the_archive_command(
        self, config: AppConfig, archive: Path
    ) -> None:
        result = _invoke(
            config,
            "trend-timing",
            "--universe", "trading",
            "--archive-dir", str(archive),
            *SYMBOLS, *WINDOW,
        )  # fmt: skip

        assert "--dataset klines_1h" in str(result.exception)
