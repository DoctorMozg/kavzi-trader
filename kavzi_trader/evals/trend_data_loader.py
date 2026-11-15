import logging
from pathlib import Path

import pandas as pd

from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.dataset_builder import MS_PER_DAY
from kavzi_trader.evals.series_cache import TIME, VALUE, SeriesCache
from kavzi_trader.evals.trend_data_schema import TrendDataSchema

logger = logging.getLogger(__name__)

CANDLES_PER_DAY = 6


class TrendDataLoader:
    """Builds daily closes from cached 4h candles and daily funding sums."""

    def __init__(self, cache_dir: Path) -> None:
        self._candles = CandleCache(cache_dir, "4h")
        self._funding = SeriesCache(cache_dir, "funding")

    def load(self, symbols: list[str]) -> TrendDataSchema:
        closes = pd.DataFrame({s: self._daily_close(s) for s in symbols})
        funding = pd.DataFrame({s: self._daily_funding(s) for s in symbols})
        funding = funding.reindex(closes.index).fillna(0.0)
        return TrendDataSchema(closes=closes, funding=funding)

    def _daily_close(self, symbol: str) -> pd.Series:
        frame = self._candles.load(symbol)
        if frame.empty:
            msg = f"no cached 4h candles for {symbol} in {self._candles.path(symbol)}"
            raise FileNotFoundError(msg)
        day = pd.to_datetime(frame["open_time_ms"] // MS_PER_DAY, unit="D")
        grouped = frame.groupby(day)["close"]
        close = grouped.last()[grouped.count() == CANDLES_PER_DAY]
        calendar = pd.date_range(close.index[0], close.index[-1], freq="D")
        if len(calendar) != len(close):
            msg = f"{symbol} has {len(calendar) - len(close)} missing daily bars"
            raise ValueError(msg)
        logger.debug("%s: %d daily bars", symbol, len(close))
        return close

    def _daily_funding(self, symbol: str) -> pd.Series:
        frame = self._funding.load(symbol)
        day = pd.to_datetime(frame[TIME] // MS_PER_DAY, unit="D")
        return frame.groupby(day)[VALUE].sum()
