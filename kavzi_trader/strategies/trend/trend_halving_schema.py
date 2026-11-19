from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TrendHalvingSchema(BaseModel):
    """A vol-spike halving of one symbol, undone at the next daily rebalance."""

    symbol: Annotated[str, Field(min_length=1)]
    hour_ms: Annotated[int, Field(ge=0)]
    rv: Annotated[float, Field(ge=0)]
    threshold: Annotated[float, Field(ge=0)]
    # Weight of equity left after the halving; held_weights keep the rule's weight.
    target_weight: Annotated[float, Field(ge=0)]

    model_config = ConfigDict(frozen=True)
