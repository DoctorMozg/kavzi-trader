from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Structured outputs strip maxLength, so the prompt states these limits too.
GATE_CATALYST_MAX_CHARS = 200
GATE_REASONING_MAX_CHARS = 500


class TrendGateDecisionSchema(BaseModel):
    """One LLM sample judging whether news contradicts a trend entry."""

    verdict: Literal["KEEP", "VETO"]
    catalyst: Annotated[str, Field(max_length=GATE_CATALYST_MAX_CHARS)]
    reasoning: Annotated[str, Field(min_length=20, max_length=GATE_REASONING_MAX_CHARS)]

    model_config = ConfigDict(frozen=True)
