import asyncio
import hashlib
import io
import logging
import zipfile
from collections import defaultdict

import httpx2
import pandas as pd

from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema
from kavzi_trader.archive.archive_listing import ArchiveListing
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.archive.archive_sync_schema import ArchiveSyncSchema
from kavzi_trader.archive.checksum_mismatch_error import ChecksumMismatchError

logger = logging.getLogger(__name__)

DOWNLOAD_URL = "https://data.binance.vision/"
# Spot archives switched to microseconds in 2025; fail loudly if USD-M follows.
_MAX_MS = 10**14
_EPOCH = pd.Timestamp("1970-01-01")


class ArchiveDownloader:
    """Mirrors USD-M archives into the store, one checksum-verified month at a time.

    Months already stored are skipped, so an interrupted sync resumes. The
    current month is left out until it ends: a stored month counts as done.
    """

    def __init__(
        self,
        http: httpx2.AsyncClient,
        listing: ArchiveListing,
        store: ArchiveStore,
        current_month: str,
        concurrency: int = 8,
    ) -> None:
        self._http = http
        self._listing = listing
        self._store = store
        self._current_month = current_month
        self._limit = asyncio.Semaphore(concurrency)

    async def sync(
        self, dataset: ArchiveDatasetSchema, symbol: str, from_month: str
    ) -> ArchiveSyncSchema:
        by_month: dict[str, list[str]] = defaultdict(list)
        for period in await self._listing.periods(dataset, symbol):
            if from_month <= period[:7] < self._current_month:
                by_month[period[:7]].append(period)
        missing = [m for m in by_month if not self._store.has(dataset, symbol, m)]
        await asyncio.gather(
            *(self._fetch_month(dataset, symbol, m, by_month[m]) for m in missing)
        )
        logger.info(
            "%s %s: %d months fetched, %d already stored",
            symbol,
            dataset.name,
            len(missing),
            len(by_month) - len(missing),
        )
        return ArchiveSyncSchema(
            symbol=symbol,
            dataset=dataset.name,
            fetched=len(missing),
            skipped=len(by_month) - len(missing),
        )

    async def _fetch_month(
        self,
        dataset: ArchiveDatasetSchema,
        symbol: str,
        month: str,
        periods: list[str],
    ) -> None:
        parts = await asyncio.gather(
            *(self._fetch(dataset, symbol, p) for p in periods)
        )
        rows = pd.concat(parts, ignore_index=True).drop_duplicates(ignore_index=True)
        self._store.write(dataset, symbol, month, rows)

    async def _fetch(
        self, dataset: ArchiveDatasetSchema, symbol: str, period: str
    ) -> pd.DataFrame:
        stem = dataset.file_stem(symbol, period)
        url = f"{DOWNLOAD_URL}{dataset.prefix}{dataset.symbol_dir(symbol)}/{stem}.zip"
        async with self._limit:
            archive = await self._http.get(url)
            archive.raise_for_status()
            published = await self._http.get(f"{url}.CHECKSUM")
            published.raise_for_status()
        expected = published.text.split()[0]
        actual = hashlib.sha256(archive.content).hexdigest()
        if actual != expected:
            msg = f"{stem}.zip sha256 {actual} but Binance publishes {expected}"
            raise ChecksumMismatchError(msg)
        return parse_archive_csv(dataset, archive.content, f"{stem}.csv")


def parse_archive_csv(
    dataset: ArchiveDatasetSchema, content: bytes, member: str
) -> pd.DataFrame:
    """Archive CSV rows under the dataset's columns; old files have no header."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        text = archive.read(member)
    has_header = not text[:1].isdigit()
    raw = pd.read_csv(io.BytesIO(text), header=0 if has_header else None)
    if dataset.source_columns is not None:
        absent = set(dataset.source_columns) - set(raw.columns)
        if absent:
            msg = f"{member} lacks columns {sorted(absent)}"
            raise ValueError(msg)
        raw = raw[dataset.source_columns]
    width = len(dataset.columns)
    if raw.shape[1] < width:
        msg = f"{member} has {raw.shape[1]} columns, expected {width}"
        raise ValueError(msg)
    # Klines carry a trailing unused "ignore" column.
    rows = raw.iloc[:, :width].set_axis(dataset.columns, axis=1)
    for column in (c for c in dataset.columns if c.endswith("time_ms")):
        if not pd.api.types.is_numeric_dtype(rows[column]):
            # Metrics stamp rows as "YYYY-MM-DD HH:MM:SS" UTC.
            stamps = pd.to_datetime(rows[column])
            rows[column] = (stamps - _EPOCH) // pd.Timedelta(milliseconds=1)
        elif (rows[column] >= _MAX_MS).any():
            msg = f"{member} column {column} is not in milliseconds"
            raise ValueError(msg)
    return rows
