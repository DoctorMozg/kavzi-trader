from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema


class TrendStateSchema(BaseModel):
    """What the trend plugin must remember across restarts."""

    # Start of the last check slot that ran (a UTC day, or a 6h slot).
    last_check_ms: Annotated[int | None, Field(ge=0)] = None
    weights: Annotated[dict[str, float], Field()] = {}
    # Vol-spike halvings since the last rebalance, which restores them.
    halvings: Annotated[dict[str, TrendHalvingSchema], Field()] = {}

    model_config = ConfigDict(frozen=True)
