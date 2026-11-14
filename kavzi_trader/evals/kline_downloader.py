import logging

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.evals.candle_cache import CandleCache

logger = logging.getLogger(__name__)

# Binance futures klines cap one request at 1500 rows.
_PAGE_LIMIT = 1500
_MS_PER_S = 1000


class KlineDownloader:
    """Fills the candle cache for a time range; reruns only fetch what is missing."""

    def __init__(
        self, client: ExchangeClient, cache: CandleCache, interval: str
    ) -> None:
        self._client = client
        self._cache = cache
        self._interval = interval
        self._step_ms = KLINE_INTERVALS[interval] * _MS_PER_S

    async def ensure_range(self, symbol: str, start_ms: int, end_ms: int) -> None:
        """Cache every closed candle opening in [start_ms, end_ms)."""
        if start_ms >= end_ms:
            msg = f"empty range for {symbol}: {start_ms} >= {end_ms}"
            raise ValueError(msg)
        cached = self._cache.load(symbol)
        if cached.empty:
            gaps = [(start_ms, end_ms)]
        else:
            first = int(cached["open_time_ms"].iloc[0])
            last = int(cached["open_time_ms"].iloc[-1])
            gaps = []
            if start_ms < first:
                gaps.append((start_ms, first))
            if last + self._step_ms < end_ms:
                gaps.append((last + self._step_ms, end_ms))
        if not gaps:
            logger.info("%s already cached for the requested range", symbol)
        for gap_start, gap_end in gaps:
            await self._fetch(symbol, gap_start, gap_end)

    async def _fetch(self, symbol: str, start_ms: int, end_ms: int) -> None:
        logger.info(
            "Downloading %s %s from %d to %d", symbol, self._interval, start_ms, end_ms
        )
        cursor = start_ms
        total = 0
        while cursor < end_ms:
            batch = await self._client.get_klines(
                symbol,
                self._interval,
                start_time=cursor,
                end_time=end_ms - 1,
                limit=_PAGE_LIMIT,
            )
            if not batch:
                break
            self._cache.merge(symbol, batch)
            total += len(batch)
            cursor = int(batch[-1].open_time.timestamp() * _MS_PER_S) + self._step_ms
        logger.info("Downloaded %d %s candles for %s", total, self._interval, symbol)
