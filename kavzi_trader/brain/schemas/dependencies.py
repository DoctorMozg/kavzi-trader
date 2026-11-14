from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.domain.algorithm_confluence import DualConfluenceSchema
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.indicator_schemas import TechnicalIndicatorsSchema
from kavzi_trader.domain.state_schemas import AccountStateSchema, PositionSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.external.schemas import SentimentSummarySchema
from kavzi_trader.indicators.htf import HtfTrendSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema


class AnalystDependenciesSchema(BaseModel):
    """
    Context for deeper analysis including confluence and order flow.
    """

    symbol: Annotated[str, Field(...)]
    current_price: Annotated[Decimal, Field(...)]
    timeframe: Annotated[str, Field(..., max_length=10)]
    recent_candles: Annotated[list[CandlestickSchema], Field(..., min_length=1)]
    indicators: Annotated[TechnicalIndicatorsSchema, Field(...)]
    order_flow: Annotated[OrderFlowSchema | None, Field(default=None)]
    algorithm_confluence: Annotated[DualConfluenceSchema, Field(...)]
    volatility_regime: Annotated[VolatilityRegime, Field(...)]
    htf_trend: Annotated[HtfTrendSchema | None, Field(default=None)]
    leverage: Annotated[int, Field(default=5, ge=1, le=125)]
    sentiment_summary: Annotated[
        SentimentSummarySchema | None,
        Field(default=None),
    ]
    symbol_tier: Annotated[str, Field(default="TIER_2")]
    tier_min_confidence: Annotated[Decimal, Field(default=Decimal("0.70"))]

    model_config = ConfigDict(frozen=True)


class TradingDependenciesSchema(BaseModel):
    """
    Full context required to make a final trade decision.
    """

    symbol: Annotated[str, Field(...)]
    current_price: Annotated[Decimal, Field(...)]
    timeframe: Annotated[str, Field(..., max_length=10)]
    recent_candles: Annotated[list[CandlestickSchema], Field(..., min_length=1)]
    indicators: Annotated[TechnicalIndicatorsSchema, Field(...)]
    order_flow: Annotated[OrderFlowSchema | None, Field(default=None)]
    algorithm_confluence: Annotated[DualConfluenceSchema, Field(...)]
    volatility_regime: Annotated[VolatilityRegime, Field(...)]
    htf_trend: Annotated[HtfTrendSchema | None, Field(default=None)]
    account_state: Annotated[AccountStateSchema, Field(...)]
    open_positions: Annotated[list[PositionSchema], Field(default_factory=list)]
    leverage: Annotated[int, Field(default=5, ge=1, le=125)]
    atr_history: Annotated[list[Decimal], Field(default_factory=list)]
    sentiment_summary: Annotated[
        SentimentSummarySchema | None,
        Field(default=None),
    ]
    symbol_tier: Annotated[str, Field(default="TIER_2")]
    tier_min_confidence: Annotated[Decimal, Field(default=Decimal("0.70"))]

    model_config = ConfigDict(frozen=True)
