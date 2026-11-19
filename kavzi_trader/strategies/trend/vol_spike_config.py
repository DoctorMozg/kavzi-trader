from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VolSpikeConfigSchema(BaseModel):
    """Vol-spike halving, fixed by evals/preregistrations/2026_11_19_crash_replay.md."""

    enabled: bool = True
    # A spike: an hour's 1m realized variance above this quantile of the previous
    # history_hours hours; no spike fires before min_history_hours exist.
    history_hours: Annotated[int, Field(ge=2)] = 2160
    min_history_hours: Annotated[int, Field(ge=1)] = 720
    quantile: Annotated[float, Field(gt=0, lt=1)] = 0.99
    # Share of the position kept until the next daily rebalance.
    scale: Annotated[float, Field(gt=0, lt=1)] = 0.5

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _min_within_history(self) -> Self:
        if self.min_history_hours > self.history_hours:
            msg = (
                f"min_history_hours {self.min_history_hours} exceeds "
                f"history_hours {self.history_hours}"
            )
            raise ValueError(msg)
        return self
