from pydantic import BaseModel, ConfigDict


class FundingXsSummarySchema(BaseModel):
    """Headline numbers of one run; annual figures use 365 days."""

    days: int
    annual_return: float
    annual_volatility: float
    sharpe: float | None
    # Sharpe of the return minus the 3-month T-bill rate, what idle cash earned.
    sharpe_over_cash: float | None
    max_drawdown: float
    annual_turnover: float
    annual_price_return: float
    annual_funding_return: float
    annual_cost_return: float
    yearly_return: dict[int, float]

    model_config = ConfigDict(frozen=True)
