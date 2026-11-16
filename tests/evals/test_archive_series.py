from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.candle_cache import COLUMNS
from tests.archive.conftest import (
    MINUTE_MS,
    write_bars,
    write_funding,
    write_metrics,
)

JAN_31_MS = 1_580_428_800_000  # 2020-01-31
HOUR_MS = 3_600_000


def _minutes(start_ms: int, count: int) -> pd.DataFrame:
    step = np.arange(count, dtype=float)
    open_ms = start_ms + np.arange(count) * MINUTE_MS
    return pd.DataFrame(
        {
            "open_time_ms": open_ms,
            "open": 100 + step,
            "high": 110 + step,
            "low": 90 + step,
            "close": 101 + step,
            "volume": 1.0,
            "close_time_ms": open_ms + MINUTE_MS - 1,
            "quote_volume": 2.0,
            "trades_count": 3,
            "taker_buy_base_volume": 0.5,
            "taker_buy_quote_volume": 1.0,
        },
        columns=list(COLUMNS),
    )


@pytest.fixture
def series(tmp_path: Path) -> ArchiveSeries:
    return ArchiveSeries(tmp_path)


class TestCandles:
    def test_minutes_roll_up_across_stored_months(
        self, tmp_path: Path, series: ArchiveSeries
    ) -> None:
        # Two hours on each side of the Feb 1 boundary, stored as two months.
        minutes = _minutes(JAN_31_MS + 22 * HOUR_MS, 240)
        store = ArchiveStore(tmp_path)
        store.write(ARCHIVE_DATASETS["klines"], "X", "2020-02", minutes[120:])
        store.write(ARCHIVE_DATASETS["klines"], "X", "2020-01", minutes[:120])

        bars = series.candles("X", "1h")

        assert list(bars.columns) == list(COLUMNS)
        assert bars["open_time_ms"].tolist() == [
            JAN_31_MS + h * HOUR_MS for h in (22, 23, 24, 25)
        ]
        first = bars.iloc[0]
        assert (first.open, first.high, first.low, first.close) == (100, 169, 90, 160)
        assert (first.volume, first.trades_count) == (60, 180)
        assert first.close_time_ms == JAN_31_MS + 23 * HOUR_MS - 1

    def test_archived_bars_load_back_unchanged(
        self, tmp_path: Path, series: ArchiveSeries
    ) -> None:
        bars = _minutes(JAN_31_MS, 4).assign(
            open_time_ms=JAN_31_MS + np.arange(4) * 4 * HOUR_MS,
            close_time_ms=lambda f: f.open_time_ms + 4 * HOUR_MS - 1,
        )
        write_bars(tmp_path, "X", bars, 4 * HOUR_MS)

        pd.testing.assert_frame_equal(series.candles("X", "4h"), bars)

    @pytest.mark.parametrize("interval", ["1w", "7m", "bogus"])
    def test_bars_must_start_at_utc_midnight(
        self, series: ArchiveSeries, interval: str
    ) -> None:
        with pytest.raises(ValueError, match="does not divide a UTC day"):
            series.candles("X", interval)

    def test_a_symbol_never_archived_is_an_error(self, series: ArchiveSeries) -> None:
        with pytest.raises(FileNotFoundError, match="no archived 1m klines for X"):
            series.candles("X", "4h")


def test_funding_rates_load_as_time_and_value(
    tmp_path: Path, series: ArchiveSeries
) -> None:
    write_funding(tmp_path, "X", [JAN_31_MS + 8 * HOUR_MS, JAN_31_MS], 0.0001)

    funding = series.funding("X")

    assert list(funding.columns) == ["time_ms", "value"]
    assert funding["time_ms"].tolist() == [JAN_31_MS, JAN_31_MS + 8 * HOUR_MS]
    assert funding["value"].tolist() == [0.0001, 0.0001]


def test_metrics_load_sorted_in_cache_columns(
    tmp_path: Path, series: ArchiveSeries
) -> None:
    # Binance republished some daily metrics files with rows out of order.
    times = [JAN_31_MS + 600_000, JAN_31_MS, JAN_31_MS + 300_000]
    write_metrics(
        tmp_path,
        "X",
        pd.DataFrame(
            {
                "time_ms": times,
                "open_interest": [3.0, 1.0, 2.0],
                "global_ratio": 1.2,
                "top_position_ratio": 1.1,
            }
        ),
    )

    metrics = series.metrics("X")

    assert list(metrics.columns) == [
        "time_ms",
        "open_interest",
        "global_ratio",
        "top_position_ratio",
    ]
    assert metrics["time_ms"].tolist() == sorted(times)
    assert metrics["open_interest"].tolist() == [1.0, 2.0, 3.0]
