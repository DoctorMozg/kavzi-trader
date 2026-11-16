from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TrialSchema(BaseModel):
    """One backtested variant; every variant tried counts against the best one."""

    model_config = ConfigDict(frozen=True)

    # Strategies compared against each other, e.g. "trend".
    family: Annotated[str, Field(min_length=1)]
    # Everything that makes this variant differ from its siblings.
    variant: Annotated[str, Field(min_length=1)]
    first_day: str
    last_day: str
    daily_net: Annotated[list[float], Field(min_length=3)]

    @property
    def key(self) -> str:
        return f"{self.family}|{self.variant}|{self.first_day}|{self.last_day}"
