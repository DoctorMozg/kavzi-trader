from collections.abc import AsyncIterator
from pathlib import Path

import httpx2
import pandas as pd
import pytest
import pytest_asyncio

from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema
from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_downloader import ArchiveDownloader
from kavzi_trader.archive.archive_listing import ArchiveListing
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.archive.checksum_mismatch_error import ChecksumMismatchError
from kavzi_trader.archive.vision_client import VisionClient
from tests.archive.conftest import (
    METRICS_HEADER,
    NO_WAIT,
    FakeVision,
    daily_kline_key,
    kline_csv,
    kline_key,
    metrics_key,
)

KLINES = ARCHIVE_DATASETS["klines"]
FUNDING = ARCHIVE_DATASETS["funding"]
METRICS = ARCHIVE_DATASETS["metrics"]
JAN_MS = 1_577_836_800_000  # 2020-01-01
DAY_MS = 86_400_000
FEB_MS = 1_580_515_200_000  # 2020-02-01


@pytest.fixture
def store(tmp_path: Path) -> ArchiveStore:
    return ArchiveStore(tmp_path / "archive")


@pytest.fixture
def delisted(vision: FakeVision) -> FakeVision:
    # Early archives have no header row; later ones do.
    vision.add(
        kline_key("SRMUSDT", "2020-01"),
        "SRMUSDT-1m-2020-01.csv",
        kline_csv(JAN_MS, header=False),
    )
    vision.add(
        kline_key("SRMUSDT", "2020-02"),
        "SRMUSDT-1m-2020-02.csv",
        kline_csv(FEB_MS, header=True),
    )
    vision.add(
        kline_key("BTCUSDT", "2020-01"),
        "BTCUSDT-1m-2020-01.csv",
        kline_csv(JAN_MS, header=False),
    )
    return vision


@pytest_asyncio.fixture
async def http(delisted: FakeVision) -> AsyncIterator[VisionClient]:
    transport = httpx2.MockTransport(delisted.handler)
    async with httpx2.AsyncClient(transport=transport) as client:
        yield VisionClient(client, NO_WAIT)


@pytest.fixture
def downloader(http: VisionClient, store: ArchiveStore) -> ArchiveDownloader:
    return ArchiveDownloader(http, ArchiveListing(http), store, current_month="2099-01")


async def _sync(
    downloader: ArchiveDownloader,
    symbol: str,
    from_month: str = "2020-01",
    dataset: ArchiveDatasetSchema = KLINES,
) -> tuple[int, int]:
    done = await downloader.sync(dataset, symbol, from_month)
    return done.fetched, done.skipped


class TestMonthlyArchives:
    async def test_months_with_and_without_a_header_load_as_one_series(
        self, downloader: ArchiveDownloader, store: ArchiveStore
    ) -> None:
        assert await _sync(downloader, "SRMUSDT") == (2, 0)

        rows = store.load(KLINES, "SRMUSDT")
        assert list(rows.columns) == KLINES.columns
        assert rows["open_time_ms"].is_monotonic_increasing
        assert rows["open_time_ms"].iloc[[0, -1]].tolist() == [JAN_MS, FEB_MS + 120_000]
        assert rows["close"].eq(1.5).all()

    async def test_a_rerun_fetches_only_new_months(
        self, downloader: ArchiveDownloader, delisted: FakeVision
    ) -> None:
        await _sync(downloader, "SRMUSDT")
        delisted.downloads.clear()

        assert await _sync(downloader, "SRMUSDT") == (0, 2)
        assert delisted.downloads == []

    async def test_months_before_the_start_are_left_out(
        self, downloader: ArchiveDownloader, store: ArchiveStore
    ) -> None:
        assert await _sync(downloader, "SRMUSDT", "2020-02") == (1, 0)
        assert store.months(KLINES, "SRMUSDT") == ["2020-02"]

    async def test_a_checksum_mismatch_stores_nothing(
        self, downloader: ArchiveDownloader, delisted: FakeVision, store: ArchiveStore
    ) -> None:
        key = kline_key("SRMUSDT", "2020-01")
        delisted.checksums[key] = "0" * 64 + "  SRMUSDT-1m-2020-01.zip"

        with pytest.raises(ChecksumMismatchError, match=r"SRMUSDT-1m-2020-01\.zip"):
            await _sync(downloader, "SRMUSDT", "2020-01")

        assert "2020-01" not in store.months(KLINES, "SRMUSDT")

    async def test_days_a_monthly_file_lacks_come_from_daily_files(
        self, downloader: ArchiveDownloader, delisted: FakeVision, store: ArchiveStore
    ) -> None:
        # The monthly file stops after Jan 1; Binance still has the Jan 2 daily file.
        for day, first_ms in (("2020-01-01", JAN_MS), ("2020-01-02", JAN_MS + DAY_MS)):
            delisted.add(
                daily_kline_key("SRMUSDT", day),
                f"SRMUSDT-1m-{day}.csv",
                kline_csv(first_ms, header=True),
            )

        await _sync(downloader, "SRMUSDT", "2020-01")

        times = store.load(KLINES, "SRMUSDT")["open_time_ms"]
        assert times.tolist() == [
            *(JAN_MS + i * 60_000 for i in range(3)),
            *(JAN_MS + DAY_MS + i * 60_000 for i in range(3)),
            *(FEB_MS + i * 60_000 for i in range(3)),
        ]
        daily = [d for d in delisted.downloads if "/daily/" in d]
        assert daily == [daily_kline_key("SRMUSDT", "2020-01-02")]

    async def test_funding_columns_are_renamed(
        self, downloader: ArchiveDownloader, delisted: FakeVision, store: ArchiveStore
    ) -> None:
        stem = FUNDING.file_stem("BTCUSDT", "2020-01")
        key = f"{FUNDING.prefix}{FUNDING.symbol_dir('BTCUSDT')}/{stem}.zip"
        text = f"calc_time,funding_interval_hours,last_funding_rate\n{JAN_MS},8,-0.0001"
        delisted.add(key, f"{stem}.csv", text)

        await _sync(downloader, "BTCUSDT", dataset=FUNDING)

        assert store.load(FUNDING, "BTCUSDT").to_dict("records") == [
            {"time_ms": JAN_MS, "interval_hours": 8, "rate": -0.0001}
        ]


class TestDailyArchives:
    @pytest.fixture
    def metrics(self, delisted: FakeVision) -> FakeVision:
        for day in ("2020-01-01", "2020-01-02", "2020-02-01"):
            row = f"{day} 00:05:00,BTCUSDT,100,1000,1.1,1.2,1.3,0.9"
            # The archive repeats rows at times.
            text = f"{METRICS_HEADER}\n{row}\n{row}"
            delisted.add(
                metrics_key("BTCUSDT", day), f"BTCUSDT-metrics-{day}.csv", text
            )
        return delisted

    async def test_days_are_stored_as_one_file_per_month(
        self, metrics: FakeVision, downloader: ArchiveDownloader, store: ArchiveStore
    ) -> None:
        assert await _sync(downloader, "BTCUSDT", dataset=METRICS) == (2, 0)

        rows = store.load(METRICS, "BTCUSDT")
        assert store.months(METRICS, "BTCUSDT") == ["2020-01", "2020-02"]
        assert rows["time_ms"].tolist() == [
            JAN_MS + 300_000,
            JAN_MS + 86_400_000 + 300_000,
            FEB_MS + 300_000,
        ]
        assert rows.iloc[0].to_dict() == {
            "time_ms": JAN_MS + 300_000,
            "open_interest": 100,
            "open_interest_value": 1000,
            "top_account_ratio": 1.1,
            "top_position_ratio": 1.2,
            "global_ratio": 1.3,
            "taker_volume_ratio": 0.9,
        }

    async def test_the_month_in_progress_waits_until_it_ends(
        self, metrics: FakeVision, http: VisionClient, store: ArchiveStore
    ) -> None:
        downloader = ArchiveDownloader(
            http, ArchiveListing(http), store, current_month="2020-02"
        )

        assert await _sync(downloader, "BTCUSDT", dataset=METRICS) == (1, 0)
        assert store.months(METRICS, "BTCUSDT") == ["2020-01"]


class TestArchiveListing:
    async def test_periods_follow_every_page_and_skip_checksum_keys(
        self, http: VisionClient
    ) -> None:
        assert await ArchiveListing(http).periods(KLINES, "SRMUSDT") == [
            "2020-01",
            "2020-02",
        ]


def test_an_empty_symbol_loads_as_an_empty_frame(store: ArchiveStore) -> None:
    rows = store.load(KLINES, "NONEUSDT")

    assert rows.empty
    assert list(rows.columns) == KLINES.columns


def test_a_month_is_written_whole_or_not_at_all(tmp_path: Path) -> None:
    store = ArchiveStore(tmp_path)
    rows = pd.DataFrame({"time_ms": [1], "interval_hours": [8], "rate": [0.1]})

    store.write(FUNDING, "X", "2020-01", rows)

    assert not list(tmp_path.rglob("*.partial"))
    assert store.load(FUNDING, "X")["time_ms"].dtype == "int64"
