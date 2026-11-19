from typing import Protocol

import pandas as pd


class VolForecaster(Protocol):
    """Annualised variance over the 7 days after each close, known at that close."""

    @property
    def name(self) -> str: ...

    def forecast(self, returns: pd.DataFrame) -> pd.DataFrame:
        """Same shape as the daily log ``returns``; NaN where no forecast exists."""
        ...
