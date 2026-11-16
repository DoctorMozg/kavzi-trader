import logging
from pathlib import Path

from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.metrics_cache import MetricsCache
from kavzi_trader.evals.series_cache import SeriesCache
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.replay.replay_data_schema import ReplayDataSchema
from kavzi_trader.replay.replay_needs_schema import ReplayNeedsSchema

logger = logging.getLogger(__name__)


class ReplayDataLoader:
    """Reads the eval cache that `eval refresh-cache` fills."""

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir

    def load(self, needs: ReplayNeedsSchema) -> ReplayDataSchema:
        bars = CandleCache(self._dir, needs.interval)
        candles = {}
        for symbol in needs.symbols:
            frame = bars.load(symbol)
            if frame.empty:
                msg = f"no cached {needs.interval} candles at {bars.path(symbol)}"
                raise FileNotFoundError(msg)
            candles[symbol] = frame.sort_values("open_time_ms", ignore_index=True)
        funding = SeriesCache(self._dir, "funding")
        metrics = MetricsCache(self._dir)
        logger.info(
            "Replay data: %d symbols, %d %s bars",
            len(needs.symbols),
            sum(len(f) for f in candles.values()),
            needs.interval,
        )
        return ReplayDataSchema(
            interval=needs.interval,
            candles=candles,
            funding={s: funding.load(s) for s in needs.symbols},
            metrics=(
                {s: metrics.load(s) for s in needs.symbols} if needs.metrics else {}
            ),
            daily_closes=(
                TrendDataLoader(self._dir).load(needs.symbols).closes
                if needs.daily_closes
                else None
            ),
        )
