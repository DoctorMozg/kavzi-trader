from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema


class TrendResultSchema(BaseModel):
    """One universe's backtest outcome; drags are annualised return points."""

    model_config = ConfigDict(frozen=True)

    symbols: list[str]
    first_day: str
    last_day: str
    days: int
    net: TrendStatsSchema
    benchmark: TrendStatsSchema
    turnover_per_year: float
    cost_drag: float
    funding_drag: float
    # Net return of each scored day, oldest first; trial statistics read it.
    daily_net: list[float]
