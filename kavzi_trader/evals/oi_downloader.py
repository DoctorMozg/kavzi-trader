import logging

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.evals.series_cache import TIME, SeriesCache

logger = logging.getLogger(__name__)

# Binance caps GET /futures/data/openInterestHist at 500 rows per request.
_PAGE_LIMIT = 500
_MS_PER_S = 1000


class OiDownloader:
    """Fills the open interest cache; Binance serves only about the last 30 days.

    Each page names its own end time: given only a start, the endpoint returns
    the latest rows rather than the ones after the start.
    """

    def __init__(self, client: ExchangeClient, cache: SeriesCache, period: str) -> None:
        self._client = client
        self._cache = cache
        self._period = period
        self._period_ms = KLINE_INTERVALS[period] * _MS_PER_S

    async def ensure_range(self, symbol: str, start_ms: int, end_ms: int) -> None:
        """Cache every snapshot in [start_ms, end_ms)."""
        if start_ms >= end_ms:
            msg = f"empty range for {symbol}: {start_ms} >= {end_ms}"
            raise ValueError(msg)
        cached = self._cache.load(symbol)
        if cached.empty:
            gaps = [(start_ms, end_ms)]
        else:
            first = int(cached[TIME].iloc[0])
            last = int(cached[TIME].iloc[-1])
            gaps = []
            if start_ms < first - self._period_ms:
                gaps.append((start_ms, first))
            if last + self._period_ms < end_ms:
                gaps.append((last + 1, end_ms))
        for gap_start, gap_end in gaps:
            await self._fetch(symbol, gap_start, gap_end)

    async def _fetch(self, symbol: str, start_ms: int, end_ms: int) -> None:
        cursor = start_ms
        total = 0
        while cursor < end_ms:
            page_end = min(end_ms - 1, cursor + (_PAGE_LIMIT - 1) * self._period_ms)
            batch = await self._client.get_open_interest_history(
                symbol,
                period=self._period,
                limit=_PAGE_LIMIT,
                start_time=cursor,
                end_time=page_end,
            )
            self._cache.merge(
                symbol,
                [int(r["timestamp"]) for r in batch],
                [float(r["sumOpenInterest"]) for r in batch],
            )
            total += len(batch)
            cursor = page_end + 1
        logger.info("Downloaded %d %s OI snapshots for %s", total, self._period, symbol)
