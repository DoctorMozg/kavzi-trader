from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class TradeValidationParamsSchema(BaseModel):
    """Trade inputs for one DynamicRiskValidator.validate_trade call."""

    symbol: str
    side: Literal["LONG", "SHORT"]
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    current_atr: Decimal
    atr_history: list[Decimal]
    leverage: Annotated[int, Field(default=1)]
    confidence: Annotated[Decimal | None, Field(default=None)]
    symbol_tier: Annotated[str, Field(default="TIER_2")]
    size_multiplier: Annotated[Decimal, Field(default=Decimal(1))]

    model_config = ConfigDict(frozen=True)
