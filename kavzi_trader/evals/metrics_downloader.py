import asyncio
import io
import logging
import zipfile

import pandas as pd

from kavzi_trader.archive.vision_client import VisionClient
from kavzi_trader.evals.metrics_cache import (
    GLOBAL_RATIO,
    OPEN_INTEREST,
    TIME,
    TOP_POSITION_RATIO,
    MetricsCache,
)

logger = logging.getLogger(__name__)

_URL = (
    "https://data.binance.vision/data/futures/um/daily/metrics/"
    "{symbol}/{symbol}-metrics-{day}.zip"
)
_MS_PER_DAY = 86_400_000
_BATCH_DAYS = 32
_NOT_FOUND = 404
# count_long_short_ratio is the global account ratio and
# sum_toptrader_long_short_ratio the top-trader position ratio, matched against
# the REST endpoints on 2026-11-16.
_COLUMNS = {
    "sum_open_interest": OPEN_INTEREST,
    "count_long_short_ratio": GLOBAL_RATIO,
    "sum_toptrader_long_short_ratio": TOP_POSITION_RATIO,
}
_EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


class MetricsDownloader:
    """Fills the metrics cache from the data.binance.vision daily archive.

    Only days with no cached rows are fetched. A day the archive does not have
    is a gap, not an error, and is asked for again on the next run.
    """

    def __init__(
        self, http: VisionClient, cache: MetricsCache, concurrency: int = 8
    ) -> None:
        self._http = http
        self._cache = cache
        self._limit = asyncio.Semaphore(concurrency)

    async def ensure_range(self, symbol: str, start_ms: int, end_ms: int) -> None:
        """Cache every archive day touching [start_ms, end_ms)."""
        if start_ms >= end_ms:
            msg = f"empty range for {symbol}: {start_ms} >= {end_ms}"
            raise ValueError(msg)
        cached = self._cache.load(symbol)
        have = set((cached[TIME] // _MS_PER_DAY).tolist())
        wanted = range(start_ms // _MS_PER_DAY, (end_ms - 1) // _MS_PER_DAY + 1)
        missing = [d for d in wanted if d not in have]
        gaps = 0
        for i in range(0, len(missing), _BATCH_DAYS):
            days = missing[i : i + _BATCH_DAYS]
            parts = await asyncio.gather(*(self._fetch_day(symbol, d) for d in days))
            found = [p for p in parts if p is not None]
            gaps += len(parts) - len(found)
            if found:
                self._cache.merge(symbol, pd.concat(found, ignore_index=True))
        logger.info(
            "%s metrics: %d days fetched, %d not in the archive",
            symbol,
            len(missing) - gaps,
            gaps,
        )

    async def _fetch_day(self, symbol: str, day: int) -> pd.DataFrame | None:
        stamp = pd.Timestamp(day * _MS_PER_DAY, unit="ms").date().isoformat()
        async with self._limit:
            response = await self._http.get(_URL.format(symbol=symbol, day=stamp))
        if response.status_code == _NOT_FOUND:
            logger.debug("%s metrics for %s not in the archive", symbol, stamp)
            return None
        response.raise_for_status()
        return self._parse(symbol, stamp, response.content)

    @staticmethod
    def _parse(symbol: str, stamp: str, content: bytes) -> pd.DataFrame | None:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            raw = pd.read_csv(archive.open(f"{symbol}-metrics-{stamp}.csv"))
        absent = {"create_time", *_COLUMNS} - set(raw.columns)
        if absent:
            msg = f"{symbol} metrics {stamp} lacks columns {sorted(absent)}"
            raise ValueError(msg)
        if raw.empty:
            return None
        created = pd.to_datetime(raw["create_time"]).dt.tz_localize("UTC")
        rows = raw[list(_COLUMNS)].rename(columns=_COLUMNS).astype("float64")
        rows.insert(0, TIME, (created - _EPOCH) // pd.Timedelta(milliseconds=1))
        return rows
