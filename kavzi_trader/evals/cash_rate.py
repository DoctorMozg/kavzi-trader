import logging
from pathlib import Path

import pandas as pd

from kavzi_trader.strategies.trend.donchian_trend_signal import DAYS_PER_YEAR

logger = logging.getLogger(__name__)

# FRED TB3MS: 3-month US T-bill secondary market rate, monthly average, percent.
CASH_RATE_PATH = Path("evals/cash/tb3ms_monthly.csv")


class CashRate:
    """What idle cash earned each day, from annual rates by calendar month."""

    def __init__(self, monthly: pd.Series) -> None:
        if monthly.empty:
            msg = "cash rate needs at least one month"
            raise ValueError(msg)
        self._monthly = monthly.sort_index()

    @classmethod
    def from_csv(cls, path: Path = CASH_RATE_PATH) -> CashRate:
        frame = pd.read_csv(path, parse_dates=["observation_date"])
        rates = frame["TB3MS"].to_numpy() / 100
        return cls(pd.Series(rates, index=pd.DatetimeIndex(frame["observation_date"])))

    @classmethod
    def constant(cls, annual_rate: float) -> CashRate:
        return cls(pd.Series([annual_rate], index=[pd.Timestamp("1970-01-01")]))

    def daily(self, days: pd.DatetimeIndex) -> pd.Series:
        months = days.to_period("M").to_timestamp()
        first, last = self._monthly.index[0], self._monthly.index[-1]
        if months.min() < first:
            msg = f"cash rates start {first.date()}, days start {days.min().date()}"
            raise ValueError(msg)
        if months.max() > last:
            logger.warning(
                "Cash rates end %s; later days reuse that month's rate", last.date()
            )
        rates = self._monthly.reindex(months, method="ffill").to_numpy()
        return pd.Series(rates / DAYS_PER_YEAR, index=days)
