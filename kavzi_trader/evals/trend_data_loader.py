import logging

import pandas as pd

from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.dataset_builder import MS_PER_DAY
from kavzi_trader.evals.series_cache import TIME, VALUE
from kavzi_trader.evals.trend_data_schema import TrendDataSchema

logger = logging.getLogger(__name__)

CANDLES_PER_DAY = 6


class TrendDataLoader:
    """Builds daily closes from archived 4h candles and daily funding sums."""

    def __init__(self, archive: ArchiveSeries) -> None:
        self._archive = archive

    def load(self, symbols: list[str]) -> TrendDataSchema:
        closes = pd.DataFrame({s: self._daily_close(s) for s in symbols})
        funding = pd.DataFrame({s: self._daily_funding(s) for s in symbols})
        funding = funding.reindex(closes.index).fillna(0.0)
        return TrendDataSchema(closes=closes, funding=funding)

    def _daily_close(self, symbol: str) -> pd.Series:
        frame = self._archive.candles(symbol, "4h")
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
        frame = self._archive.funding(symbol)
        day = pd.to_datetime(frame[TIME] // MS_PER_DAY, unit="D")
        return frame.groupby(day)[VALUE].sum()
