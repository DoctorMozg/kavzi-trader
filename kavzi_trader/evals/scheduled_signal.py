import numpy as np
import pandas as pd

from kavzi_trader.evals.signal_period_schema import SignalPeriodSchema


class ScheduledSignal:
    """Hands each return day to the signal scheduled for it; other days hold nothing.

    Every signal sees the full history, so path-dependent state carries across
    period boundaries as it would live.
    """

    def __init__(self, periods: list[SignalPeriodSchema]) -> None:
        if not periods:
            msg = "need at least one signal period"
            raise ValueError(msg)
        self._periods = periods

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        # Weights set at close d earn day d+1, so a row belongs to d+1's period.
        return_day = (closes.index + pd.Timedelta(days=1)).date
        out = np.zeros(closes.shape)
        for period in self._periods:
            rows = (return_day >= period.first_day) & (return_day <= period.last_day)
            out[rows] = period.signal.weights(closes)[rows]
        return out
