from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.domain.candlestick import CandlestickSchema


class AnonymizedCaseSchema(BaseModel):
    """History ending at the decision candle, with identity and scale removed."""

    case_id: Annotated[str, Field(...)]
    symbol: Annotated[str, Field(...)]
    candles: Annotated[list[CandlestickSchema], Field(..., min_length=1)]
    price_factor: Annotated[Decimal, Field(..., gt=0)]
    volume_factor: Annotated[Decimal, Field(..., gt=0)]
    time_shift_ms: Annotated[int, Field(...)]

    model_config = ConfigDict(frozen=True)

    def to_real_price(self, anonymized_price: Decimal) -> Decimal:
        return anonymized_price / self.price_factor
