import numpy as np
import pandas as pd

from kavzi_trader.evals.donchian_trend_signal import DAYS_PER_YEAR
from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema

MIN_DAYS = 2


class TrendMetrics:
    """Return statistics from daily returns on a UTC day index."""

    def stats(self, returns: pd.Series) -> TrendStatsSchema:
        if returns.empty:
            msg = "cannot compute stats of an empty return series"
            raise ValueError(msg)
        equity = (1.0 + returns).cumprod()
        years = len(returns) / DAYS_PER_YEAR
        return TrendStatsSchema(
            annual_return=float(equity.iloc[-1] ** (1.0 / years) - 1.0),
            annual_vol=float(returns.std() * np.sqrt(DAYS_PER_YEAR)),
            sharpe=self.sharpe(returns),
            max_drawdown=float((equity / equity.cummax() - 1.0).min()),
            sharpe_by_year={
                int(year): self.sharpe(chunk)
                for year, chunk in returns.groupby(returns.index.year)
            },
        )

    @staticmethod
    def sharpe(returns: pd.Series) -> float | None:
        std = returns.std()
        if len(returns) < MIN_DAYS or not std > 0:
            return None
        return float(returns.mean() / std * np.sqrt(DAYS_PER_YEAR))
