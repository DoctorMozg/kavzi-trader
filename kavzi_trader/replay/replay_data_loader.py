import logging
from pathlib import Path

from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.series_cache import SeriesCache
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.replay.replay_data_schema import ReplayDataSchema

logger = logging.getLogger(__name__)

BAR_INTERVAL = "4h"


class ReplayDataLoader:
    """Reads the eval cache that `eval refresh-cache` fills."""

    def __init__(self, cache_dir: Path) -> None:
        self._candles = CandleCache(cache_dir, BAR_INTERVAL)
        self._funding = SeriesCache(cache_dir, "funding")
        self._daily = TrendDataLoader(cache_dir)

    def load(self, symbols: list[str]) -> ReplayDataSchema:
        candles = {}
        for symbol in symbols:
            frame = self._candles.load(symbol)
            if frame.empty:
                msg = (
                    f"no cached {BAR_INTERVAL} candles at {self._candles.path(symbol)}"
                )
                raise FileNotFoundError(msg)
            candles[symbol] = frame.sort_values("open_time_ms", ignore_index=True)
        funding = {s: self._funding.load(s) for s in symbols}
        logger.info(
            "Replay data: %d symbols, %d bars",
            len(symbols),
            sum(len(f) for f in candles.values()),
        )
        return ReplayDataSchema(
            candles=candles,
            funding=funding,
            daily_closes=self._daily.load(symbols).closes,
        )
