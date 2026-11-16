from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TrendStateSchema(BaseModel):
    """What the trend plugin must remember across restarts."""

    last_rebalance_day: Annotated[date | None, Field()] = None
    weights: Annotated[dict[str, float], Field()] = {}

    model_config = ConfigDict(frozen=True)
