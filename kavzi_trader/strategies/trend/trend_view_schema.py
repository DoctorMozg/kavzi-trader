from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.trend.trend_symbol_view_schema import (
    TrendSymbolViewSchema,
)


class TrendViewSchema(BaseModel):
    """The trend rule's state for every symbol, reported once per UTC day."""

    day: Annotated[date, Field()]
    lookback: Annotated[int, Field(ge=1)]
    next_rebalance_ms: Annotated[int, Field(ge=0)]
    # False when the view is a restart re-report of a day already rebalanced.
    rebalanced: Annotated[bool, Field()]
    symbols: Annotated[list[TrendSymbolViewSchema], Field()]
    # Raw rule target and the buffered weight actually held, per symbol.
    target_weights: Annotated[dict[str, float], Field()]
    held_weights: Annotated[dict[str, float], Field()]

    model_config = ConfigDict(frozen=True)
