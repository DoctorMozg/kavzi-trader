from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ReplayLlmUsageSchema(BaseModel):
    """How a replay's LLM calls were answered, and whether the window is clean."""

    model_config = ConfigDict(frozen=True)

    models: list[str]
    provider_calls: Annotated[int, Field(ge=0)]
    # Requests a replay-only run could not answer from the tape.
    tape_misses: Annotated[int, Field(ge=0)]
    # The window starts before some model's training cutoff.
    contaminated: bool
