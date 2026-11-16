import numpy as np
import pandas as pd

from kavzi_trader.strategies.trend.trend_following_plugin import DAY_MS


class HistoricalDailyCloses:
    """DailyCloseProvider over stored closes: only days already closed at now_ms."""

    def __init__(self, closes: pd.DataFrame) -> None:
        self._closes = closes

    async def closes(self, symbol: str, days: int, now_ms: int) -> np.ndarray:
        series = self._closes[symbol].dropna()
        # The index unit varies with pandas (us here), so pin it before reading ints.
        day_ms = pd.DatetimeIndex(series.index).as_unit("ms").asi8
        # Day d is final once day d + 1 starts.
        closed = series.to_numpy()[day_ms + DAY_MS <= now_ms]
        result: np.ndarray = closed[-days:]
        return result
