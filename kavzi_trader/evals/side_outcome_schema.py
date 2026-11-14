from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.barrier_enums import BarrierOutcome


class SideOutcomeSchema(BaseModel):
    """How one side's bracket resolved: barrier hit, bars to exit, R at exit."""

    outcome: Annotated[BarrierOutcome, Field(...)]
    bars_to_exit: Annotated[int, Field(..., ge=1)]
    r_multiple: Annotated[float, Field(...)]

    model_config = ConfigDict(frozen=True)
