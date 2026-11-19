from pydantic import BaseModel, ConfigDict


class MarketAlphaSchema(BaseModel):
    """Daily returns regressed on the market: what is left after its beta."""

    model_config = ConfigDict(frozen=True)

    days: int
    alpha_annual: float
    beta: float
    # Newey-West t-statistic of the intercept.
    alpha_t: float
