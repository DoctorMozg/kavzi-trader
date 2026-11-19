import asyncio
import logging

import numpy as np
import pandas as pd

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.strategies.trend.hourly_variance_schema import HourlyVarianceSchema

logger = logging.getLogger(__name__)

MINUTE_MS = 60_000
HOUR_MS = 3_600_000
PAGE_LIMIT = 1000
# A 1000-bar page weighs 5; the pause keeps a 90-day backfill near 600 weight/min.
PAGE_PAUSE_S = 0.5


class MinuteVarianceSource:
    """Hourly realized variance from Binance 1m klines, as VolSpikeHalving has it."""

    def __init__(
        self, exchange: ExchangeClient, page_pause_s: float = PAGE_PAUSE_S
    ) -> None:
        self._exchange = exchange
        self._pause_s = page_pause_s

    async def hours(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> list[HourlyVarianceSchema]:
        if start_ms % HOUR_MS or end_ms % HOUR_MS:
            msg = f"hour bounds required, got {start_ms}..{end_ms}"
            raise ValueError(msg)
        # One minute before the first hour gives its first return.
        closes = await self._closes(symbol, start_ms - MINUTE_MS, end_ms)
        if len(closes) < 2:  # noqa: PLR2004 - one return needs two closes
            return []
        log_ret = np.log(closes).diff()
        hour_ms = closes.index // HOUR_MS * HOUR_MS
        rv = log_ret.pow(2).groupby(hour_ms).sum()
        last = closes.groupby(hour_ms).last()
        return [
            HourlyVarianceSchema(hour_ms=int(h), rv=float(rv[h]), close=float(last[h]))
            for h in rv.index
            if h >= start_ms
        ]

    async def _closes(self, symbol: str, start_ms: int, end_ms: int) -> pd.Series:
        closes: dict[int, float] = {}
        cursor_ms, pages = start_ms, 0
        while cursor_ms < end_ms:
            candles = await self._exchange.get_klines(
                symbol,
                "1m",
                start_time=cursor_ms,
                end_time=end_ms - 1,
                limit=PAGE_LIMIT,
            )
            pages += 1
            for candle in candles:
                closes[int(candle.open_time.timestamp() * 1000)] = float(
                    candle.close_price
                )
            if len(candles) < PAGE_LIMIT:
                break
            cursor_ms = int(candles[-1].open_time.timestamp() * 1000) + MINUTE_MS
            await asyncio.sleep(self._pause_s)
        logger.debug("Fetched %d 1m bars of %s in %d pages", len(closes), symbol, pages)
        return pd.Series(closes, dtype=float).sort_index()
