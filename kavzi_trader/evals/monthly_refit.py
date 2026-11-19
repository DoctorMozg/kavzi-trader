from collections.abc import Iterator

import pandas as pd

from kavzi_trader.evals.realized_variance import HORIZON_DAYS


class MonthlyRefit:
    """Walk-forward schedule: refit at each month start on targets already realized."""

    def __init__(self, first_forecast_day: pd.Timestamp) -> None:
        self._first = first_forecast_day

    def months(
        self, days: pd.DatetimeIndex
    ) -> Iterator[tuple[pd.Timestamp, pd.Series]]:
        """(month start, mask of days forecast with that month's fit)."""
        starts = pd.date_range(
            self._first.to_period("M").to_timestamp(), days.max(), freq="MS"
        )
        for start in starts:
            end = start + pd.offsets.MonthBegin(1)
            mask = (days >= max(start, self._first)) & (days < end)
            if mask.any():
                yield start, pd.Series(mask, index=days)

    @staticmethod
    def train_mask(days: pd.Series, month_start: pd.Timestamp) -> pd.Series:
        """Rows whose 7-day target ended before the refit day."""
        result: pd.Series = days + pd.Timedelta(days=HORIZON_DAYS) < month_start
        return result
