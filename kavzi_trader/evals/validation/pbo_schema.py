from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class PboSchema(BaseModel):
    """Probability of Backtest Overfitting from combinatorially symmetric CV."""

    model_config = ConfigDict(frozen=True)

    # Share of splits whose in-sample winner ranks in the bottom half out of sample.
    pbo: Annotated[float, Field(ge=0, le=1)]
    n_combinations: Annotated[int, Field(ge=1)]
    # Logit of the in-sample winner's relative out-of-sample rank, per split.
    logits: list[float]
