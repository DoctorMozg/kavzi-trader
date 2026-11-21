from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IntradayClosesSchema(BaseModel):
    """Closes of closed intraday bars, oldest first, with each bar's open time."""

    open_time_ms: Annotated[list[int], Field()]
    closes: Annotated[list[float], Field()]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _same_length(self) -> IntradayClosesSchema:
        if len(self.open_time_ms) != len(self.closes):
            msg = f"{len(self.open_time_ms)} open times but {len(self.closes)} closes"
            raise ValueError(msg)
        return self
