from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrendParamsSchema(BaseModel):
    """Rule constants of the Donchian trend ensemble, fixed by the preregistration."""

    model_config = ConfigDict(frozen=True)

    lookbacks: Annotated[tuple[int, ...], Field(min_length=1)] = (20, 40, 80)
    vol_window: Annotated[int, Field(ge=2)] = 30
    annual_vol_target: Annotated[float, Field(gt=0)] = 0.25
    max_leverage: Annotated[float, Field(gt=0)] = 2.0
    long_short: bool = False

    @model_validator(mode="after")
    def _positive_lookbacks(self) -> Self:
        if any(lb < 1 for lb in self.lookbacks):
            msg = f"lookbacks must be positive, got {self.lookbacks}"
            raise ValueError(msg)
        return self
