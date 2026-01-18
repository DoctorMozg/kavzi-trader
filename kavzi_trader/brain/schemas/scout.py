from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScoutDecisionSchema(BaseModel):
    """
    Quick triage result for whether a market snapshot is worth deeper analysis.

    The Scout agent does a fast scan and only decides if something looks
    interesting enough to justify a deeper, slower analysis step.
    """

    verdict: Annotated[Literal["INTERESTING", "SKIP"], Field(...)]
    reason: Annotated[str, Field(..., max_length=140)]
    pattern_detected: Annotated[str | None, Field(default=None, max_length=100)]

    model_config = ConfigDict(frozen=True)
