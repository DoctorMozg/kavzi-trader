from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.funding_xs_day_schema import FundingXsDaySchema


class FundingXsRunSchema(BaseModel):
    """Daily marks of one backtest plus its trading counts."""

    days: list[FundingXsDaySchema]
    rebalances: Annotated[int, Field(ge=0)]
    skipped_rebalances: Annotated[int, Field(ge=0)]
    turnover: Annotated[float, Field(ge=0)]

    model_config = ConfigDict(frozen=True)
