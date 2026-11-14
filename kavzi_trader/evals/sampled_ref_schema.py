from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.barrier_enums import CaseLabel


class SampledRefSchema(BaseModel):
    """A chosen candidate: which symbol's candle (by position) and its strata."""

    symbol: Annotated[str, Field(...)]
    bar_index: Annotated[int, Field(..., ge=0)]
    label: Annotated[CaseLabel, Field(...)]
    regime: Annotated[str, Field(...)]

    model_config = ConfigDict(frozen=True)
