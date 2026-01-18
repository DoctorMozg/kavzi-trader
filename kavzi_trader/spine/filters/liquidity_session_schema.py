from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.spine.filters.liquidity_period import LiquidityPeriod


class LiquiditySessionSchema(BaseModel):
    """Defines a UTC time window and its expected liquidity band."""

    period: Annotated[LiquidityPeriod, Field(...)]
    start_hour: Annotated[int, Field(..., ge=0, le=23)]
    end_hour: Annotated[int, Field(..., ge=0, le=23)]

    model_config = ConfigDict(frozen=True)
