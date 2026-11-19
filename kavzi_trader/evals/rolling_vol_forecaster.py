import numpy as np
import pandas as pd

from kavzi_trader.evals.realized_variance import VARIANCE_FLOOR
from kavzi_trader.strategies.trend.donchian_trend_signal import DAYS_PER_YEAR


class RollingVolForecaster:
    """The paper rule's estimate: sample std of the last ``window`` log returns."""

    def __init__(self, window: int = 30) -> None:
        self._window = window

    @property
    def name(self) -> str:
        return f"rolling-{self._window}d"

    def forecast(self, returns: pd.DataFrame) -> pd.DataFrame:
        std = returns.rolling(self._window, min_periods=self._window).std()
        variance: pd.DataFrame = (std.pow(2) * DAYS_PER_YEAR).clip(lower=VARIANCE_FLOOR)
        return variance.where(np.isfinite(variance))
