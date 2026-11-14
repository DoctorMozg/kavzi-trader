from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.brain.geometry.schemas import TradeGeometrySchema
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema

TraderStopReason = Literal[
    "no_candles",
    "circuit_open",
    "dedup_hit",
    "pre_trade_gate_reject",
    "geometry_reject",
    "structure_invalid",
    "llm_timeout",
    "llm_unexpected_model",
    "llm_error",
    "ok",
]


class TraderPipelineResultSchema(BaseModel):
    """Outcome of the Trader pipeline stage.

    Carries everything ``AgentRouter.run`` needs to build the final
    ``PipelineResult``. ``decision`` is None when the Trader was not
    invoked (e.g. empty candles, unhandled exception); otherwise it is a
    real Trader decision, a cached dedup hit, a deterministic gate WAIT,
    a circuit-open WAIT, or an LLM-failure fallback WAIT.

    ``deps`` is None only when ``get_trader`` returned empty candles or
    the Trader raised a generic unhandled exception.

    ``geometry`` carries the concrete entry/SL/TP derived for an actionable
    LONG/SHORT decision; it is None for WAIT/CLOSE and every reject path.
    """

    decision: Annotated[TradeDecisionSchema | None, Field(default=None)]
    deps: Annotated[TradingDependenciesSchema | None, Field(default=None)]
    geometry: Annotated[TradeGeometrySchema | None, Field(default=None)]
    cached: Annotated[bool, Field(default=False)]
    reason: Annotated[TraderStopReason, Field(...)]

    model_config = ConfigDict(frozen=True)
