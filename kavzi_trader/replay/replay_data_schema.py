import pandas as pd
from pydantic import BaseModel, ConfigDict


class ReplayDataSchema(BaseModel):
    """Per-symbol 4h candles and funding settlements, plus daily closes."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # CandleCache columns, sorted by open_time_ms.
    candles: dict[str, pd.DataFrame]
    # SeriesCache columns: settlement time_ms and the funding rate value.
    funding: dict[str, pd.DataFrame]
    # One column per symbol, indexed by UTC day, as TrendDataLoader builds them.
    daily_closes: pd.DataFrame
