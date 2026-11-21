from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TrendRuleStateSchema(BaseModel):
    """One symbol's long/flat state now and at each daily close it was given."""

    state: Annotated[float, Field(ge=0, le=1)]
    # One per daily close, oldest first: the state after that day's last check.
    day_states: Annotated[list[float], Field()]

    model_config = ConfigDict(frozen=True)
