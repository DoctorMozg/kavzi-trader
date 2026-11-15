import io
import zipfile
from pathlib import Path
from typing import cast

import httpx2
import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.metrics_alignment import MetricsAlignment
from kavzi_trader.evals.metrics_cache import (
    GLOBAL_RATIO,
    OPEN_INTEREST,
    TIME,
    TOP_POSITION_RATIO,
    MetricsCache,
)
from kavzi_trader.evals.metrics_downloader import MetricsDownloader
from kavzi_trader.evals.series_cache import VALUE

DAY_MS = 86_400_000
DAY0 = 20_000  # 2024-10-04 UTC, as days since the epoch
HEADER = (
    "create_time,symbol,sum_open_interest,sum_open_interest_value,"
    "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
    "count_long_short_ratio,sum_taker_long_short_vol_ratio"
)


def _stamp(day: int) -> str:
    return str(pd.Timestamp(day * DAY_MS, unit="ms").date())


def day_zip(symbol: str, day: int) -> bytes:
    rows = [
        f"{_stamp(day)} {hh:02d}:00:00,{symbol},{100 + hh},0,9,{2 + hh},{1 + hh},0"
        for hh in (0, 1)
    ]
    rows.append(rows[0])  # the archive repeats rows at times
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            f"{symbol}-metrics-{_stamp(day)}.csv", "\n".join([HEADER, *rows])
        )
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            msg = f"HTTP {self.status_code}"
            raise RuntimeError(msg)


class FakeArchive:
    """Serves daily metrics zips by day; days outside ``days`` are 404."""

    def __init__(self, days: set[int], broken: int | None = None) -> None:
        self.days = days
        self.broken = broken
        self.requested: list[str] = []

    async def get(self, url: str) -> FakeResponse:
        self.requested.append(url)
        stamp = url.rsplit("-metrics-", 1)[1].removesuffix(".zip")
        day = int(pd.Timestamp(stamp).timestamp() * 1000) // DAY_MS
        if day == self.broken:
            return FakeResponse(500)
        if day not in self.days:
            return FakeResponse(404)
        return FakeResponse(200, day_zip("BTCUSDT", day))


@pytest.fixture
def cache(tmp_path: Path) -> MetricsCache:
    return MetricsCache(tmp_path / "cache")


def _downloader(archive: FakeArchive, cache: MetricsCache) -> MetricsDownloader:
    return MetricsDownloader(cast("httpx2.AsyncClient", archive), cache)


class TestMetricsDownloader:
    async def test_caches_rows_with_the_mapped_columns(
        self, cache: MetricsCache
    ) -> None:
        archive = FakeArchive({DAY0})

        await _downloader(archive, cache).ensure_range(
            "BTCUSDT", DAY0 * DAY_MS, (DAY0 + 1) * DAY_MS
        )

        rows = cache.load("BTCUSDT")
        assert rows[TIME].tolist() == [DAY0 * DAY_MS, DAY0 * DAY_MS + 3_600_000]
        assert rows[OPEN_INTEREST].tolist() == [100.0, 101.0]
        assert rows[TOP_POSITION_RATIO].tolist() == [2.0, 3.0]
        assert rows[GLOBAL_RATIO].tolist() == [1.0, 2.0]

    async def test_missing_day_is_a_gap_not_an_error(self, cache: MetricsCache) -> None:
        archive = FakeArchive({DAY0, DAY0 + 2})

        await _downloader(archive, cache).ensure_range(
            "BTCUSDT", DAY0 * DAY_MS, (DAY0 + 3) * DAY_MS
        )

        days = {t // DAY_MS for t in cache.load("BTCUSDT")[TIME]}
        assert days == {DAY0, DAY0 + 2}

    async def test_rerun_fetches_only_the_days_still_missing(
        self, cache: MetricsCache
    ) -> None:
        first = FakeArchive({DAY0, DAY0 + 1})
        await _downloader(first, cache).ensure_range(
            "BTCUSDT", DAY0 * DAY_MS, (DAY0 + 3) * DAY_MS
        )
        second = FakeArchive({DAY0, DAY0 + 1, DAY0 + 2})

        await _downloader(second, cache).ensure_range(
            "BTCUSDT", DAY0 * DAY_MS, (DAY0 + 3) * DAY_MS
        )

        assert len(second.requested) == 1
        assert _stamp(DAY0 + 2) in second.requested[0]
        assert {t // DAY_MS for t in cache.load("BTCUSDT")[TIME]} == {
            DAY0,
            DAY0 + 1,
            DAY0 + 2,
        }

    async def test_server_error_propagates_and_keeps_earlier_batches(
        self, cache: MetricsCache
    ) -> None:
        archive = FakeArchive({DAY0 + i for i in range(40)}, broken=DAY0 + 35)

        with pytest.raises(RuntimeError, match="HTTP 500"):
            await _downloader(archive, cache).ensure_range(
                "BTCUSDT", DAY0 * DAY_MS, (DAY0 + 40) * DAY_MS
            )

        # The first batch of 32 days was written before the failing one.
        assert len({t // DAY_MS for t in cache.load("BTCUSDT")[TIME]}) == 32

    async def test_rejects_an_empty_range(self, cache: MetricsCache) -> None:
        with pytest.raises(ValueError, match="empty range"):
            await _downloader(FakeArchive(set()), cache).ensure_range("BTCUSDT", 5, 5)


class TestMetricsAlignment:
    def test_takes_the_latest_row_at_or_before_the_close(self) -> None:
        times = np.array([100, 200, 300], dtype=np.int64)
        values = np.array([1.0, 2.0, 3.0])
        at = np.array([99, 100, 299, 300, 10_000], dtype=np.int64)

        out = MetricsAlignment.latest_at_or_before(times, values, at)

        assert np.isnan(out[0])
        assert out[1:].tolist() == [1.0, 2.0, 3.0, 3.0]

    def test_oi_grid_never_uses_a_row_after_the_grid_time(self) -> None:
        metrics = pd.DataFrame(
            {
                TIME: [0, 290, 310, 700],
                OPEN_INTEREST: [10.0, 20.0, 30.0, 40.0],
                GLOBAL_RATIO: 1.0,
                TOP_POSITION_RATIO: 1.0,
            }
        )

        grid = MetricsAlignment.oi_grid(metrics, 300)

        assert grid[TIME].tolist() == [0, 300, 600]
        # 300 sees the row at 290, 600 the row at 310.
        assert grid[VALUE].tolist() == [10.0, 20.0, 30.0]

    def test_oi_grid_of_nothing_is_empty(self) -> None:
        empty = pd.DataFrame(
            {c: pd.Series(dtype="float64") for c in (TIME, OPEN_INTEREST)}
        )
        assert MetricsAlignment.oi_grid(empty, 300).empty
