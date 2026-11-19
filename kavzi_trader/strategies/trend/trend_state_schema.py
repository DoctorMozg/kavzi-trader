from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema


class TrendStateSchema(BaseModel):
    """What the trend plugin must remember across restarts."""

    last_rebalance_day: Annotated[date | None, Field()] = None
    weights: Annotated[dict[str, float], Field()] = {}
    # Vol-spike halvings since the last rebalance, which restores them.
    halvings: Annotated[dict[str, TrendHalvingSchema], Field()] = {}

    model_config = ConfigDict(frozen=True)
