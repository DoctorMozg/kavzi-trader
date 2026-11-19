import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from pathlib import Path

import httpx2
import pandas as pd

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.archive.vision_client import VisionClient
from kavzi_trader.cli.commands.eval_options import MS_PER_S
from kavzi_trader.evals.funding_downloader import FundingDownloader
from kavzi_trader.evals.metrics_cache import MetricsCache
from kavzi_trader.evals.metrics_downloader import MetricsDownloader
from kavzi_trader.evals.oi_downloader import OiDownloader
from kavzi_trader.evals.series_cache import SeriesCache

logger = logging.getLogger(__name__)

# The live z-score needs FUNDING_HISTORY_LIMIT settlements (8h apart) of lead-in.
_FUNDING_LEAD_MS = 40 * 24 * 3600 * MS_PER_S
# Binance rejects openInterestHist start times older than about 30 days.
OI_LOOKBACK_MS = 29 * 24 * 3600 * MS_PER_S
_METRICS_TIMEOUT_S = 60.0


class MarketDataLoader:
    """Fills the eval cache with funding, OI and metrics covering candle frames.

    ``client`` is an injected exchange; without one a public client is opened per job.
    """

    def __init__(self, cache_dir: Path, client: ExchangeClient | None) -> None:
        self._cache_dir = cache_dir
        self._client = client

    def run(self, job: Callable[[ExchangeClient], Coroutine[None, None, None]]) -> None:
        """Run ``job`` on the injected client, or on a public one closed afterwards."""

        async def _public() -> None:
            public = BinanceClient()  # public market data, no credentials
            try:
                await job(public)
            finally:
                await public.close()

        asyncio.run(job(self._client) if self._client is not None else _public())

    def funding(self, frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Download missing funding settlements covering each candle frame."""
        cache = SeriesCache(self._cache_dir, "funding")

        async def _job(exchange: ExchangeClient) -> None:
            downloader = FundingDownloader(exchange, cache)
            for symbol, frame in frames.items():
                await downloader.ensure_range(
                    symbol,
                    int(frame["open_time_ms"].iloc[0]) - _FUNDING_LEAD_MS,
                    int(frame["close_time_ms"].iloc[-1]) + 1,
                )

        self.run(_job)
        return {symbol: cache.load(symbol) for symbol in frames}

    def oi(
        self, frames: dict[str, pd.DataFrame], period: str
    ) -> dict[str, pd.DataFrame]:
        """Download the OI snapshots Binance still serves that overlap each frame."""
        cache = SeriesCache(self._cache_dir, f"oi_{period}")
        oldest_ms = int(time.time() * MS_PER_S) - OI_LOOKBACK_MS

        async def _job(exchange: ExchangeClient) -> None:
            downloader = OiDownloader(exchange, cache, period)
            for symbol, frame in frames.items():
                start = max(int(frame["open_time_ms"].iloc[0]), oldest_ms)
                end = int(frame["close_time_ms"].iloc[-1]) + 1
                if start >= end:
                    logger.warning(
                        "%s candles end before the OI history starts", symbol
                    )
                    continue
                await downloader.ensure_range(symbol, start, end)

        self.run(_job)
        return {symbol: cache.load(symbol) for symbol in frames}

    def metrics(self, frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Download missing archive days covering each candle frame."""
        cache = MetricsCache(self._cache_dir)

        async def _job() -> None:
            async with httpx2.AsyncClient(timeout=_METRICS_TIMEOUT_S) as http:
                downloader = MetricsDownloader(VisionClient(http), cache)
                for symbol, frame in frames.items():
                    await downloader.ensure_range(
                        symbol,
                        int(frame["open_time_ms"].iloc[0]),
                        int(frame["close_time_ms"].iloc[-1]) + 1,
                    )

        asyncio.run(_job())
        return {symbol: cache.load(symbol) for symbol in frames}
