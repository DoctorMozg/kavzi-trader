from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class VolSpikeReadingSchema(BaseModel):
    """One closed hour's realized variance against the spike threshold."""

    hour_ms: Annotated[int, Field(ge=0)]
    rv: Annotated[float, Field(ge=0)]
    # None until min_history_hours of history exist; no spike can fire then.
    threshold: Annotated[float | None, Field(ge=0)] = None

    model_config = ConfigDict(frozen=True)

    @property
    def spike(self) -> bool:
        return self.threshold is not None and self.rv > self.threshold
