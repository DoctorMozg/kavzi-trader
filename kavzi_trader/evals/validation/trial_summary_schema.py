from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.validation.deflated_sharpe_schema import DeflatedSharpeSchema
from kavzi_trader.evals.validation.pbo_schema import PboSchema


class TrialSummarySchema(BaseModel):
    """How much of a family's best backtest survives its own selection."""

    model_config = ConfigDict(frozen=True)

    family: str
    n_trials: Annotated[int, Field(ge=1)]
    best_variant: str
    deflated: DeflatedSharpeSchema
    # Over the trials sharing the best one's window; None when fewer than two.
    pbo: PboSchema | None
    pbo_trials: Annotated[int, Field(ge=0)]
