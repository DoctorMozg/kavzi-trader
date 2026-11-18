from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TrendDayViewSchema(BaseModel):
    """One closed day of the trend rule as the dashboard draws it."""

    day_ms: Annotated[int, Field(ge=0)]
    close: Annotated[float, Field(gt=0)]
    # Breakout levels for this day's close; None until the lookback has filled.
    upper: Annotated[float | None, Field()] = None
    lower: Annotated[float | None, Field()] = None
    signal: Annotated[float, Field(ge=-1, le=1)]

    model_config = ConfigDict(frozen=True)
