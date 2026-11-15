from pydantic import BaseModel, ConfigDict


class FundingXsDaySchema(BaseModel):
    """One daily mark; components are fractions of the prior day's equity."""

    day_ms: int
    price_return: float
    funding_return: float
    cost_return: float
    equity: float

    model_config = ConfigDict(frozen=True)

    @property
    def net_return(self) -> float:
        return self.price_return + self.funding_return + self.cost_return
