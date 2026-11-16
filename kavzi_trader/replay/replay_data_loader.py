import logging

from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.replay.replay_data_schema import ReplayDataSchema
from kavzi_trader.replay.replay_needs_schema import ReplayNeedsSchema

logger = logging.getLogger(__name__)


class ReplayDataLoader:
    """Reads what a replay needs from the mirrored Binance archive."""

    def __init__(self, archive: ArchiveSeries) -> None:
        self._archive = archive

    def load(self, needs: ReplayNeedsSchema) -> ReplayDataSchema:
        candles = {s: self._archive.candles(s, needs.interval) for s in needs.symbols}
        logger.info(
            "Replay data: %d symbols, %d %s bars",
            len(needs.symbols),
            sum(len(f) for f in candles.values()),
            needs.interval,
        )
        return ReplayDataSchema(
            interval=needs.interval,
            candles=candles,
            funding={s: self._archive.funding(s) for s in needs.symbols},
            metrics=(
                {s: self._archive.metrics(s) for s in needs.symbols}
                if needs.metrics
                else {}
            ),
            daily_closes=(
                TrendDataLoader(self._archive).load(needs.symbols).closes
                if needs.daily_closes
                else None
            ),
        )
