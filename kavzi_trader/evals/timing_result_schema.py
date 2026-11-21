from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.trend_result_schema import TrendResultSchema


class TimingResultSchema(BaseModel):
    """One scored arm: the usual trend result plus how often it trades."""

    model_config = ConfigDict(frozen=True)

    result: TrendResultSchema
    # Weight changes summed over symbols, per year.
    trades_per_year: float
