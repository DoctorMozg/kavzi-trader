from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DeflatedSharpeSchema(BaseModel):
    """A selected strategy's Sharpe against the best of its trials by luck alone.

    Sharpe ratios here are per period, not annualised.
    """

    model_config = ConfigDict(frozen=True)

    sharpe: float
    # Sharpe the best of n_trials skill-less trials is expected to reach.
    expected_max_sharpe: float
    # Probability the true Sharpe exceeds expected_max_sharpe; 0.95 is the usual bar.
    deflated_sharpe: Annotated[float, Field(ge=0, le=1)]
    n_trials: Annotated[int, Field(ge=1)]
    n_obs: Annotated[int, Field(ge=2)]
