from pathlib import Path

import httpx2
import pandas as pd
import pytest

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_downloader import ArchiveDownloader
from kavzi_trader.archive.archive_listing import MONTHLY_PREFIX, ArchiveListing
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.archive.checksum_mismatch_error import ChecksumMismatchError
from kavzi_trader.cli.commands.archive import is_usdt_perpetual
from tests.archive.conftest import FakeVision, kline_csv, kline_key

KLINES = ARCHIVE_DATASETS["klines"]
FUNDING = ARCHIVE_DATASETS["funding"]
JAN_MS = 1_577_836_800_000  # 2020-01-01
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


async def _sync(
    vision: FakeVision, store: ArchiveStore, symbol: str, from_month: str = "2020-01"
) -> tuple[int, int]:
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(vision.handler)
    ) as http:
        downloader = ArchiveDownloader(http, ArchiveListing(http), store)
        done = await downloader.sync(KLINES, symbol, from_month)
    return done.fetched, done.skipped


class TestArchiveDownloader:
    async def test_months_with_and_without_a_header_load_as_one_series(
        self, delisted: FakeVision, store: ArchiveStore
    ) -> None:
        assert await _sync(delisted, store, "SRMUSDT") == (2, 0)

        rows = store.load(KLINES, "SRMUSDT")
        assert list(rows.columns) == KLINES.columns
        assert rows["open_time_ms"].is_monotonic_increasing
        assert rows["open_time_ms"].iloc[[0, -1]].tolist() == [JAN_MS, FEB_MS + 120_000]
        assert rows["close"].eq(1.5).all()

    async def test_a_rerun_fetches_only_new_months(
        self, delisted: FakeVision, store: ArchiveStore
    ) -> None:
        await _sync(delisted, store, "SRMUSDT")
        delisted.downloads.clear()

        assert await _sync(delisted, store, "SRMUSDT") == (0, 2)
        assert delisted.downloads == []

    async def test_months_before_the_start_are_left_out(
        self, delisted: FakeVision, store: ArchiveStore
    ) -> None:
        assert await _sync(delisted, store, "SRMUSDT", "2020-02") == (1, 0)
        assert not store.has(KLINES, "SRMUSDT", "2020-01")

    async def test_a_checksum_mismatch_stores_nothing(
        self, delisted: FakeVision, store: ArchiveStore
    ) -> None:
        key = kline_key("SRMUSDT", "2020-01")
        delisted.checksums[key] = "0" * 64 + "  SRMUSDT-1m-2020-01.zip"

        with pytest.raises(ChecksumMismatchError, match=r"SRMUSDT-1m-2020-01\.zip"):
            await _sync(delisted, store, "SRMUSDT", "2020-01")

        assert not store.has(KLINES, "SRMUSDT", "2020-01")

    async def test_funding_columns_are_renamed(
        self, vision: FakeVision, store: ArchiveStore
    ) -> None:
        key = f"{MONTHLY_PREFIX}fundingRate/BTCUSDT/BTCUSDT-fundingRate-2020-01.zip"
        text = f"calc_time,funding_interval_hours,last_funding_rate\n{JAN_MS},8,-0.0001"
        vision.add(key, "BTCUSDT-fundingRate-2020-01.csv", text)
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(vision.handler)
        ) as http:
            await ArchiveDownloader(http, ArchiveListing(http), store).sync(
                FUNDING, "BTCUSDT", "2020-01"
            )

        rows = store.load(FUNDING, "BTCUSDT")
        assert rows.to_dict("records") == [
            {"time_ms": JAN_MS, "interval_hours": 8, "rate": -0.0001}
        ]


class TestArchiveListing:
    async def test_symbols_follow_every_listing_page(
        self, delisted: FakeVision
    ) -> None:
        delisted.add(kline_key("ETHUSDT", "2020-01"), "x.csv", "")
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(delisted.handler)
        ) as http:
            symbols = await ArchiveListing(http).symbols("klines")

        assert symbols == ["BTCUSDT", "ETHUSDT", "SRMUSDT"]

    async def test_months_skip_checksum_keys(self, delisted: FakeVision) -> None:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(delisted.handler)
        ) as http:
            months = await ArchiveListing(http).months("klines/SRMUSDT/1m")

        assert months == ["2020-01", "2020-02"]


def test_an_empty_symbol_loads_as_an_empty_frame(store: ArchiveStore) -> None:
    rows = store.load(KLINES, "NONEUSDT")

    assert rows.empty
    assert list(rows.columns) == KLINES.columns


@pytest.mark.parametrize(
    ("symbol", "perpetual"),
    [
        ("BTCUSDT", True),
        ("SRMUSDT", True),
        ("BTCUSDT_230331", False),
        ("BTCUSDC", False),
    ],
)
def test_only_usdt_perpetuals_are_mirrored_by_default(
    symbol: str, perpetual: bool
) -> None:
    assert is_usdt_perpetual(symbol) is perpetual


def test_rows_are_typed_like_the_archive(tmp_path: Path) -> None:
    store = ArchiveStore(tmp_path)
    store.write(
        FUNDING,
        "X",
        "2020-01",
        pd.DataFrame({"time_ms": [1], "interval_hours": [8], "rate": [0.1]}),
    )

    assert not list(tmp_path.rglob("*.partial"))
    assert store.load(FUNDING, "X")["time_ms"].dtype == "int64"
