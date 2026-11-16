import hashlib
import io
import zipfile
from pathlib import Path

import httpx2
import numpy as np
import pandas as pd
import pytest

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.evals.candle_cache import COLUMNS

KLINE_HEADER = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
    "taker_buy_volume,taker_buy_quote_volume,ignore"
)

METRICS_HEADER = (
    "create_time,symbol,sum_open_interest,sum_open_interest_value,"
    "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
    "count_long_short_ratio,sum_taker_long_short_vol_ratio"
)


def kline_csv(first_ms: int, *, header: bool) -> str:
    rows = [
        f"{first_ms + i * 60_000},1.0,2.0,0.5,1.5,10,{first_ms + i * 60_000 + 59_999},"
        "15,3,4,6,0"
        for i in range(3)
    ]
    return "\n".join([KLINE_HEADER, *rows] if header else rows)


def zipped(member: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, text)
    return buffer.getvalue()


class FakeVision:
    """Serves S3 listings, zips and CHECKSUM files the way data.binance.vision does."""

    def __init__(self, page_size: int = 1000) -> None:
        self.files: dict[str, bytes] = {}
        self.checksums: dict[str, str] = {}
        self.downloads: list[str] = []
        self._page_size = page_size

    def add(self, key: str, member: str, text: str) -> None:
        content = zipped(member, text)
        self.files[key] = content
        digest = hashlib.sha256(content).hexdigest()
        self.checksums[key] = f"{digest}  {key.rsplit('/', 1)[-1]}"

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path.lstrip("/")
        if request.url.host.startswith("s3-"):
            return self._listing(request)
        if path.endswith(".CHECKSUM"):
            return httpx2.Response(
                200, text=self.checksums[path.removesuffix(".CHECKSUM")]
            )
        self.downloads.append(path)
        return httpx2.Response(200, content=self.files[path])

    def _listing(self, request: httpx2.Request) -> httpx2.Response:
        prefix = request.url.params["prefix"]
        marker = request.url.params.get("marker", "")
        keys = sorted(k for k in self.files if k.startswith(prefix))
        entries = [e for k in keys for e in (k, k + ".CHECKSUM")]
        tag = "<Contents><Key>{}</Key></Contents>"
        rest = [e for e in entries if e > marker]
        page = rest[: self._page_size]
        truncated = len(rest) > len(page)
        body = "".join(tag.format(e) for e in page)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>{str(truncated).lower()}</IsTruncated>{body}"
            "</ListBucketResult>"
        )
        return httpx2.Response(200, content=xml.encode())


def kline_key(symbol: str, month: str) -> str:
    klines = ARCHIVE_DATASETS["klines"]
    stem = klines.file_stem(symbol, month)
    return f"{klines.prefix}{klines.symbol_dir(symbol)}/{stem}.zip"


def daily_kline_key(symbol: str, day: str) -> str:
    klines = ARCHIVE_DATASETS["klines"]
    stem = klines.file_stem(symbol, day)
    return f"data/futures/um/daily/{klines.symbol_dir(symbol)}/{stem}.zip"


def metrics_key(symbol: str, day: str) -> str:
    metrics = ARCHIVE_DATASETS["metrics"]
    stem = metrics.file_stem(symbol, day)
    return f"{metrics.prefix}{metrics.symbol_dir(symbol)}/{stem}.zip"


@pytest.fixture
def vision() -> FakeVision:
    return FakeVision(page_size=2)


MINUTE_MS = 60_000
_SUMMED = [
    "volume",
    "quote_volume",
    "trades_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]


def _by_month(rows: pd.DataFrame, time_column: str) -> dict[str, pd.DataFrame]:
    months = pd.to_datetime(rows[time_column], unit="ms").dt.strftime("%Y-%m")
    return {m: part.reset_index(drop=True) for m, part in rows.groupby(months)}


def write_bars(root: Path, symbol: str, bars: pd.DataFrame, bar_ms: int) -> None:
    """Archives each bar as 1m klines that roll back up to exactly that bar."""
    per_bar = bar_ms // MINUTE_MS
    first = np.arange(len(bars) * per_bar) % per_bar == 0
    minutes = bars.loc[bars.index.repeat(per_bar), list(COLUMNS)].reset_index(drop=True)
    minutes["open_time_ms"] += np.tile(np.arange(per_bar) * MINUTE_MS, len(bars))
    minutes["close_time_ms"] = minutes["open_time_ms"] + MINUTE_MS - 1
    # The first minute carries the bar's range and volume; the rest sit at its close.
    for column in ("open", "high", "low"):
        minutes.loc[~first, column] = minutes.loc[~first, "close"]
    minutes.loc[~first, _SUMMED] = 0
    store = ArchiveStore(root)
    for month, rows in _by_month(minutes, "open_time_ms").items():
        store.write(ARCHIVE_DATASETS["klines"], symbol, month, rows)


def write_funding(root: Path, symbol: str, times_ms: list[int], rate: float) -> None:
    rows = pd.DataFrame({"time_ms": times_ms, "interval_hours": 8, "rate": rate})
    store = ArchiveStore(root)
    for month, part in _by_month(rows, "time_ms").items():
        store.write(ARCHIVE_DATASETS["funding"], symbol, month, part)


def write_metrics(root: Path, symbol: str, rows: pd.DataFrame) -> None:
    """Archives rows of the MetricsCache columns; the other archive columns are 0."""
    metrics = ARCHIVE_DATASETS["metrics"]
    full = rows.reindex(columns=metrics.columns, fill_value=0.0)
    store = ArchiveStore(root)
    for month, part in _by_month(full, "time_ms").items():
        store.write(metrics, symbol, month, part)
