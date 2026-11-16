import asyncio
import hashlib
import io
import logging
import zipfile

import httpx2
import pandas as pd

from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema
from kavzi_trader.archive.archive_listing import MONTHLY_PREFIX, ArchiveListing
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.archive.archive_sync_schema import ArchiveSyncSchema
from kavzi_trader.archive.checksum_mismatch_error import ChecksumMismatchError

logger = logging.getLogger(__name__)

DOWNLOAD_URL = "https://data.binance.vision/"
# Spot archives switched to microseconds in 2025; fail loudly if USD-M follows.
_MAX_MS = 10**14


class ArchiveDownloader:
    """Mirrors monthly USD-M archives into the store, checksum-verified.

    Months already stored are skipped, so an interrupted sync resumes.
    """

    def __init__(
        self,
        http: httpx2.AsyncClient,
        listing: ArchiveListing,
        store: ArchiveStore,
        concurrency: int = 8,
    ) -> None:
        self._http = http
        self._listing = listing
        self._store = store
        self._limit = asyncio.Semaphore(concurrency)

    async def sync(
        self, dataset: ArchiveDatasetSchema, symbol: str, from_month: str
    ) -> ArchiveSyncSchema:
        months = [
            m
            for m in await self._listing.months(dataset.symbol_dir(symbol))
            if m >= from_month
        ]
        missing = [m for m in months if not self._store.has(dataset, symbol, m)]
        await asyncio.gather(*(self._fetch(dataset, symbol, m) for m in missing))
        logger.info(
            "%s %s: %d months fetched, %d already stored",
            symbol,
            dataset.name,
            len(missing),
            len(months) - len(missing),
        )
        return ArchiveSyncSchema(
            symbol=symbol,
            dataset=dataset.name,
            fetched=len(missing),
            skipped=len(months) - len(missing),
        )

    async def _fetch(
        self, dataset: ArchiveDatasetSchema, symbol: str, month: str
    ) -> None:
        stem = dataset.file_stem(symbol, month)
        url = f"{DOWNLOAD_URL}{MONTHLY_PREFIX}{dataset.symbol_dir(symbol)}/{stem}.zip"
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
        rows = parse_archive_csv(dataset, archive.content, f"{stem}.csv")
        self._store.write(dataset, symbol, month, rows)


def parse_archive_csv(
    dataset: ArchiveDatasetSchema, content: bytes, member: str
) -> pd.DataFrame:
    """Archive CSV rows under the dataset's columns; old files have no header."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        text = archive.read(member)
    has_header = not text[:1].isdigit()
    raw = pd.read_csv(io.BytesIO(text), header=0 if has_header else None)
    width = len(dataset.columns)
    if raw.shape[1] < width:
        msg = f"{member} has {raw.shape[1]} columns, expected {width}"
        raise ValueError(msg)
    # Klines carry a trailing unused "ignore" column.
    rows = raw.iloc[:, :width].set_axis(dataset.columns, axis=1)
    for column in (c for c in dataset.columns if c.endswith("time_ms")):
        if (rows[column] >= _MAX_MS).any():
            msg = f"{member} column {column} is not in milliseconds"
            raise ValueError(msg)
    return rows
