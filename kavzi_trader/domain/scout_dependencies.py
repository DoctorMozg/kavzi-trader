from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.indicator_schemas import TechnicalIndicatorsSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime


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
