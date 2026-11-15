import logging

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.evals.funding_cache import FundingCache

logger = logging.getLogger(__name__)

# Binance caps GET /fapi/v1/fundingRate at 1000 rows per request.
_PAGE_LIMIT = 1000
# Longest Binance settlement interval; a smaller head gap holds no settlement.
_MAX_SETTLEMENT_GAP_MS = 8 * 3600 * 1000


class FundingDownloader:
    """Fills the funding cache for a time range; reruns only fetch what is missing."""

    def __init__(self, client: ExchangeClient, cache: FundingCache) -> None:
        self._client = client
        self._cache = cache

    async def ensure_range(self, symbol: str, start_ms: int, end_ms: int) -> None:
        """Cache every settlement in [start_ms, end_ms)."""
        if start_ms >= end_ms:
            msg = f"empty range for {symbol}: {start_ms} >= {end_ms}"
            raise ValueError(msg)
        cached = self._cache.load(symbol)
        if cached.empty:
            gaps = [(start_ms, end_ms)]
        else:
            first = int(cached["funding_time_ms"].iloc[0])
            last = int(cached["funding_time_ms"].iloc[-1])
            gaps = []
            if start_ms < first - _MAX_SETTLEMENT_GAP_MS:
                gaps.append((start_ms, first))
            if last + 1 < end_ms:
                gaps.append((last + 1, end_ms))
        for gap_start, gap_end in gaps:
            await self._fetch(symbol, gap_start, gap_end)

    async def _fetch(self, symbol: str, start_ms: int, end_ms: int) -> None:
        cursor = start_ms
        total = 0
        while cursor < end_ms:
            batch = await self._client.get_funding_rate(
                symbol, limit=_PAGE_LIMIT, start_time=cursor, end_time=end_ms - 1
            )
            if not batch:
                break
            self._cache.merge(symbol, batch)
            total += len(batch)
            cursor = int(batch[-1]["fundingTime"]) + 1
            if len(batch) < _PAGE_LIMIT:
                break
        logger.info("Downloaded %d funding settlements for %s", total, symbol)
