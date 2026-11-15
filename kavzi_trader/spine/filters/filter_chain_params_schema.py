from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.indicator_schemas import TechnicalIndicatorsSchema
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema


class FilterChainParamsSchema(BaseModel):
    """Inputs for one PreTradeFilterChain evaluation."""

    symbol: str
    side: Literal["LONG", "SHORT"]
    candle: CandlestickSchema
    indicators: TechnicalIndicatorsSchema
    order_flow: OrderFlowSchema | None
    positions: list[PositionSchema]
    atr_history: list[Decimal]
    analyst_confluence_score: Annotated[int | None, Field(default=None)]
    # Points to lower confluence bypass thresholds when signals lack data; the
    # orchestrator derives it from the Analyst's signal-scaled gates.
    confluence_threshold_shift: Annotated[int, Field(ge=0)]
    symbol_tier: Annotated[str, Field(default="TIER_2")]
    confidence: Annotated[Decimal | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)
