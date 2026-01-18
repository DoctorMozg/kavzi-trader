from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema


class DecisionLogSchema(BaseModel):
    """Structured audit record for LLM trade decisions."""

    timestamp: Annotated[datetime, Field(...)]
    symbol: Annotated[str, Field(...)]
    agent_tier: Annotated[Literal["scout", "analyst", "trader"], Field(...)]
    indicators: Annotated[TechnicalIndicatorsSchema, Field(...)]
    order_flow: Annotated[OrderFlowSchema | None, Field(default=None)]
    prompt_tokens: Annotated[int, Field(default=0, ge=0)]
    completion_tokens: Annotated[int, Field(default=0, ge=0)]
    latency_ms: Annotated[int, Field(default=0, ge=0)]
    raw_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    calibrated_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    decision: Annotated[TradeDecisionSchema, Field(...)]
    raw_reasoning: Annotated[str, Field(...)]

    model_config = ConfigDict(frozen=True)
