from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.spine.filters.liquidity_period import LiquidityPeriod


class FilterResultSchema(BaseModel):
    """Captures the outcome of a single filter evaluation."""

    name: Annotated[str, Field(...)]
    is_allowed: Annotated[bool, Field(...)]
    reason: Annotated[str | None, Field(default=None)] = None
    size_multiplier: Annotated[
        Decimal,
        Field(default=Decimal("1.0")),
    ] = Decimal("1.0")
    period: Annotated[LiquidityPeriod | None, Field(default=None)] = None

    model_config = ConfigDict(frozen=True)
