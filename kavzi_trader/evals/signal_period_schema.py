from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, SkipValidation

from kavzi_trader.evals.weight_signal import WeightSignal


class SignalPeriodSchema(BaseModel):
    """A signal in charge of the return days from ``first_day`` to ``last_day``."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    first_day: date
    last_day: date
    signal: Annotated[WeightSignal, SkipValidation]
