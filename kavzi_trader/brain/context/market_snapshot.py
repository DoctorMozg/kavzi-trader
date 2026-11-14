from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.indicator_schemas import TechnicalIndicatorsSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime


class MarketSnapshotSchema(BaseModel):
    """
    Compact snapshot of market state for prompt context.
    """

    symbol: Annotated[str, Field(...)]
    current_price: Annotated[Decimal, Field(...)]
    timeframe: Annotated[str, Field(..., max_length=10)]
    recent_candles: Annotated[list[CandlestickSchema], Field(..., min_length=1)]
    indicators: Annotated[TechnicalIndicatorsSchema, Field(...)]
    volatility_regime: Annotated[VolatilityRegime, Field(...)]

    model_config = ConfigDict(frozen=True)
