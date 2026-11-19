from pydantic import BaseModel, ConfigDict


class TrendStatsSchema(BaseModel):
    """Summary of one daily return series."""

    model_config = ConfigDict(frozen=True)

    annual_return: float
    annual_vol: float
    sharpe: float | None
    # Sharpe of the return minus the 3-month T-bill rate: what beats cash.
    sharpe_over_cash: float | None
    max_drawdown: float
    sharpe_by_year: dict[int, float | None]
