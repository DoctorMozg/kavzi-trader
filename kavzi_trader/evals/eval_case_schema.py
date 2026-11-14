from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.barrier_enums import CaseLabel
from kavzi_trader.evals.generator_params_schema import GeneratorParamsSchema
from kavzi_trader.evals.side_outcome_schema import SideOutcomeSchema


class EvalCaseSchema(BaseModel):
    """One frozen evaluation case: where to decide and what happened after."""

    case_id: Annotated[str, Field(...)]
    symbol: Annotated[str, Field(...)]
    decision_open_time_ms: Annotated[int, Field(...)]
    decision_close_time_ms: Annotated[int, Field(...)]
    interval: Annotated[str, Field(...)]
    regime: Annotated[str, Field(...)]
    atr_zscore: Annotated[float, Field(...)]
    tier: Annotated[str, Field(...)]
    entry_price: Annotated[float, Field(..., gt=0)]
    atr_14: Annotated[float, Field(..., gt=0)]
    label: Annotated[CaseLabel, Field(...)]
    long: Annotated[SideOutcomeSchema, Field(...)]
    short: Annotated[SideOutcomeSchema, Field(...)]
    sl_atr_multiple: Annotated[float, Field(..., gt=0)]
    tp_atr_multiple: Annotated[float, Field(..., gt=0)]
    dataset_version: Annotated[str, Field(...)]
    seed: Annotated[int, Field(...)]
    generator: Annotated[GeneratorParamsSchema, Field(...)]

    model_config = ConfigDict(frozen=True)
