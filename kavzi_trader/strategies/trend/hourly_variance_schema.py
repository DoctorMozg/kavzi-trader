from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class HourlyVarianceSchema(BaseModel):
    """Realized variance of one hour's 1m log returns and its last 1m close."""

    hour_ms: Annotated[int, Field(ge=0)]
    rv: Annotated[float, Field(ge=0)]
    close: Annotated[float, Field(gt=0)]

    model_config = ConfigDict(frozen=True)
