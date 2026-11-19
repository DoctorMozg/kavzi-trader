import logging
from pathlib import Path

import numpy as np
import pandas as pd

from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.crowding_xs_data_schema import CrowdingXsDataSchema
from kavzi_trader.evals.metrics_cache import MetricsCache
from kavzi_trader.evals.positioning_signals import PositioningSignals
from kavzi_trader.evals.series_cache import TIME, VALUE, SeriesCache
from kavzi_trader.evals.trend_data_schema import TrendDataSchema

logger = logging.getLogger(__name__)

DAY_MS = 86_400_000
# Metrics rows are 5-minute snapshots; Binance does not say whether a row's time
# opens or closes its interval, so each close reads the ratio one row older.
METRICS_LAG_MS = 300_000


class CrowdingXsLoader:
    """Daily closes, funding and ls_crowding ranks per symbol from the eval cache.

    A day's close is its last 4h candle's close (the bar ending 00:00 UTC), and
    its rank is the ls_crowding rank at that close. Zero-volume bars are dropped.
    """

    def __init__(self, cache_dir: Path, history: int) -> None:
        self._candles = CandleCache(cache_dir, "4h")
        self._funding = SeriesCache(cache_dir, "funding")
        self._metrics = MetricsCache(cache_dir)
        self._signals = PositioningSignals(history)

    def load(self, symbols: list[str]) -> CrowdingXsDataSchema:
        closes, ranks, funding = {}, {}, {}
        for symbol in symbols:
            frame = self._candles.load_traded(symbol)
            if frame.empty:
                logger.warning("%s: no traded 4h candles; skipped", symbol)
                continue
            rank = self._signals.crowd_rank(
                frame, self._metrics.load(symbol), METRICS_LAG_MS
            )
            ends_day = (frame["close_time_ms"].to_numpy() + 1) % DAY_MS == 0
            day = pd.to_datetime(
                frame["close_time_ms"].to_numpy()[ends_day] // DAY_MS, unit="D"
            )
            closes[symbol] = pd.Series(frame["close"].to_numpy()[ends_day], index=day)
            ranks[symbol] = pd.Series(rank[ends_day], index=day)
            settled = self._funding.load(symbol)
            settle_day = pd.to_datetime(settled[TIME] // DAY_MS, unit="D")
            funding[symbol] = settled.groupby(settle_day)[VALUE].sum()
        close_frame = pd.DataFrame(closes).sort_index()
        days = pd.date_range(close_frame.index[0], close_frame.index[-1], freq="D")
        close_frame = close_frame.reindex(days)
        data = TrendDataSchema(
            closes=close_frame,
            funding=pd.DataFrame(funding)
            .reindex(index=days, columns=close_frame.columns)
            .fillna(0.0),
        )
        rank_frame = pd.DataFrame(ranks).reindex(
            index=days, columns=close_frame.columns
        )
        logger.info(
            "Crowding XS: %d symbols, %d days, %.0f%% of symbol-days ranked",
            close_frame.shape[1],
            len(days),
            100 * float(np.mean(rank_frame.notna().to_numpy())),
        )
        return CrowdingXsDataSchema(market=data, ranks=rank_frame)
