from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict


class TrendEntrySchema(BaseModel):
    """One flat-to-long trade of the trend rule, with its net result."""

    symbol: str
    signal_day: date
    as_of: AwareDatetime
    weight: float
    exit_day: date | None
    net_pnl: float

    model_config = ConfigDict(frozen=True)
