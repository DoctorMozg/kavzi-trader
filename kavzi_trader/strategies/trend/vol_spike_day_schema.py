from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.trend.vol_spike_reading_schema import (
    VolSpikeReadingSchema,
)


class VolSpikeDaySchema(BaseModel):
    """The latest closed hour and the first spike of the current UTC day."""

    latest: Annotated[VolSpikeReadingSchema | None, Field()] = None
    first_spike: Annotated[VolSpikeReadingSchema | None, Field()] = None
    # Last 1m close seen, used to turn a quantity into a weight.
    price: Annotated[float | None, Field(gt=0)] = None

    model_config = ConfigDict(frozen=True)
