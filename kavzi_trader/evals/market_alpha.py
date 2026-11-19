import numpy as np
import pandas as pd

from kavzi_trader.evals.market_alpha_schema import MarketAlphaSchema
from kavzi_trader.strategies.trend.donchian_trend_signal import DAYS_PER_YEAR

_MIN_DAYS = 30


class MarketAlpha:
    """OLS of a daily return series on a market return, with Newey-West errors."""

    def __init__(self, lag: int = 5) -> None:
        self._lag = lag

    def regress(self, returns: pd.Series, market: pd.Series) -> MarketAlphaSchema:
        both = pd.concat([returns, market], axis=1, join="inner").dropna()
        if len(both) < _MIN_DAYS:
            msg = f"need {_MIN_DAYS} overlapping days, got {len(both)}"
            raise ValueError(msg)
        y = both.iloc[:, 0].to_numpy()
        x = np.column_stack([np.ones(len(both)), both.iloc[:, 1].to_numpy()])
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
        resid = y - x @ coef
        bread = np.linalg.inv(x.T @ x)
        scores = x * resid[:, None]
        meat = scores.T @ scores
        for k in range(1, self._lag + 1):
            weight = 1 - k / (self._lag + 1)
            cross = scores[k:].T @ scores[:-k]
            meat += weight * (cross + cross.T)
        cov = bread @ meat @ bread
        return MarketAlphaSchema(
            days=len(both),
            alpha_annual=float(coef[0] * DAYS_PER_YEAR),
            beta=float(coef[1]),
            alpha_t=float(coef[0] / np.sqrt(cov[0, 0])),
        )
