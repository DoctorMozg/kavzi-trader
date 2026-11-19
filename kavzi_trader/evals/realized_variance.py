import numpy as np
import pandas as pd

from kavzi_trader.strategies.trend.donchian_trend_signal import DAYS_PER_YEAR

HORIZON_DAYS = 7
# Annualised variance floor (vol about 3%), so a flat day has a finite log.
VARIANCE_FLOOR = 1e-3


class RealizedVariance:
    """Annualised realized variance of daily log returns, one column per symbol."""

    @staticmethod
    def log_returns(closes: pd.DataFrame) -> pd.DataFrame:
        returns: pd.DataFrame = np.log(closes).diff()
        return returns

    @staticmethod
    def backward(returns: pd.DataFrame, days: int) -> pd.DataFrame:
        """Mean squared return of the ``days`` returns up to and including t."""
        squared = returns.pow(2).rolling(days, min_periods=days).mean()
        return (squared * DAYS_PER_YEAR).clip(lower=VARIANCE_FLOOR)

    @staticmethod
    def forward(returns: pd.DataFrame, days: int = HORIZON_DAYS) -> pd.DataFrame:
        """Mean squared return of days t+1 .. t+days: what a forecast at t aims at."""
        return RealizedVariance.backward(returns, days).shift(-days)
