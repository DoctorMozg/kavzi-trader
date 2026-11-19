from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SkipValidation

from kavzi_trader.evals.weight_signal import WeightSignal


class TrendRuleSchema(BaseModel):
    """One ``eval trend`` variant: its signal, report description and trial label."""

    # A Protocol-typed wired object, not parsed data, so validation is skipped.
    signal: Annotated[WeightSignal, SkipValidation]
    description: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
