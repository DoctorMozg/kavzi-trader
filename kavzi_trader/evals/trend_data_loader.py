import logging

import pandas as pd

from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.dataset_builder import MS_PER_DAY
from kavzi_trader.evals.series_cache import TIME, VALUE
from kavzi_trader.evals.trend_data_schema import TrendDataSchema

logger = logging.getLogger(__name__)

CANDLES_PER_DAY = 6


class TrendDataLoader:
    """Builds daily closes from archived bars and daily funding sums."""

    def __init__(self, archive: ArchiveSeries) -> None:
        self._archive = archive

    def load(self, symbols: list[str]) -> TrendDataSchema:
        closes = pd.DataFrame({s: self._daily_close(s) for s in symbols})
        funding = pd.DataFrame({s: self._daily_funding(s) for s in symbols})
        funding = funding.reindex(closes.index).fillna(0.0)
        return TrendDataSchema(closes=closes, funding=funding)

    def _daily_close(self, symbol: str) -> pd.Series:
        close = self._close_from_daily_bars(symbol)
        if close is None:
            close = self._close_from_minutes(symbol)
        calendar = pd.date_range(close.index[0], close.index[-1], freq="D")
        if len(calendar) != len(close):
            msg = f"{symbol} has {len(calendar) - len(close)} missing daily bars"
            raise ValueError(msg)
        logger.debug("%s: %d daily bars", symbol, len(close))
        return close

    def _close_from_daily_bars(self, symbol: str) -> pd.Series | None:
        # Wide universes store only 1d bars; the trading symbols keep 1m history.
        bars = self._archive.daily_bars(symbol)
        if bars.empty:
            return None
        day = pd.to_datetime(bars["open_time_ms"] // MS_PER_DAY, unit="D")
        return pd.Series(bars["close"].to_numpy(dtype=float), index=day, name=symbol)

    def _close_from_minutes(self, symbol: str) -> pd.Series:
        frame = self._archive.candles(symbol, "4h")
        day = pd.to_datetime(frame["open_time_ms"] // MS_PER_DAY, unit="D")
        grouped = frame.groupby(day)["close"]
        close: pd.Series = grouped.last()[grouped.count() == CANDLES_PER_DAY]
        return close

    def _daily_funding(self, symbol: str) -> pd.Series:
        frame = self._archive.funding(symbol)
        day = pd.to_datetime(frame[TIME] // MS_PER_DAY, unit="D")
        return frame.groupby(day)[VALUE].sum()
