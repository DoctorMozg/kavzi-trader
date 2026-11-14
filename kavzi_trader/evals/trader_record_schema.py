from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema


class TraderRecordSchema(BaseModel):
    """Trader output for one case, with geometry mapped back to real prices."""

    action: str | None = None
    confidence: float | None = None
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    rr_ratio: float | None = None
    # Router stop reason: ok, pre_trade_gate_reject, geometry_reject, llm_error...
    stop_reason: str | None = None
    reasoning: str | None = None
    metrics: Annotated[StageMetricsSchema, Field(...)]

    model_config = ConfigDict(frozen=True)
