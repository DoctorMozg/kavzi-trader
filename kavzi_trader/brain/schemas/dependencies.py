from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.external.schemas import SentimentSummarySchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    DualConfluenceSchema,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import AccountStateSchema, PositionSchema

if TYPE_CHECKING:
    from kavzi_trader.api.binance.client import BinanceClient
    from kavzi_trader.events.store import RedisEventStore


def rebuild_deferred_models() -> None:
    """Call after all modules are loaded to resolve forward references."""
    from kavzi_trader.api.binance.client import (
        BinanceClient as _BinanceClient,
    )
    from kavzi_trader.events.store import (
        RedisEventStore as _RedisEventStore,
    )

    TradingDependenciesSchema.model_rebuild(
        _types_namespace={
            "BinanceClient": _BinanceClient,
            "RedisEventStore": _RedisEventStore,
        },
    )


class ScoutDependenciesSchema(BaseModel):
    """
    Context for fast triage: recent price action and quick indicators.
    """

    symbol: Annotated[str, Field(...)]
    current_price: Annotated[Decimal, Field(...)]
    timeframe: Annotated[str, Field(..., max_length=10)]
    recent_candles: Annotated[list[CandlestickSchema], Field(..., min_length=1)]
    indicators: Annotated[TechnicalIndicatorsSchema, Field(...)]
    volatility_regime: Annotated[VolatilityRegime, Field(...)]
    symbol_tier: Annotated[str, Field(default="TIER_2")]
    # Rolling window of ATR% of price, used by the adaptive compression gate.
    atr_pct_history: Annotated[list[Decimal], Field(default_factory=list)]

    model_config = ConfigDict(frozen=True)


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
    account_state: Annotated[AccountStateSchema, Field(...)]
    open_positions: Annotated[list[PositionSchema], Field(default_factory=list)]
    leverage: Annotated[int, Field(default=5, ge=1, le=125)]
    exchange_client: Annotated[BinanceClient, Field(...)]
    event_store: Annotated[RedisEventStore, Field(...)]
    atr_history: Annotated[list[Decimal], Field(default_factory=list)]
    sentiment_summary: Annotated[
        SentimentSummarySchema | None,
        Field(default=None),
    ]
    symbol_tier: Annotated[str, Field(default="TIER_2")]
    tier_min_confidence: Annotated[Decimal, Field(default=Decimal("0.70"))]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
