from pydantic import BaseModel, ConfigDict


class TrendStatsSchema(BaseModel):
    """Summary of one daily return series."""

    model_config = ConfigDict(frozen=True)

    annual_return: float
    annual_vol: float
    sharpe: float | None
    max_drawdown: float
    sharpe_by_year: dict[int, float | None]
