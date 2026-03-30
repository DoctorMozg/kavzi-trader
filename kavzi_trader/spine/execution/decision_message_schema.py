from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


class DecisionMessageSchema(BaseModel):
    """Decision payload for execution with pricing and risk context."""

    decision_id: Annotated[str, Field(...)]
    symbol: Annotated[str, Field(...)]
    action: Annotated[Literal["LONG", "SHORT", "CLOSE"], Field(...)]
    entry_price: Annotated[Decimal, Field(...)]
    stop_loss: Annotated[Decimal, Field(...)]
    take_profit: Annotated[Decimal, Field(...)]
    quantity: Annotated[Decimal, Field(...)]
    raw_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    calibrated_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    volatility_regime: Annotated[VolatilityRegime, Field(...)]
    position_management: Annotated[PositionManagementConfigSchema, Field(...)]
    created_at_ms: Annotated[int, Field(..., ge=0)]
    expires_at_ms: Annotated[int, Field(..., ge=0)]
    reasoning: Annotated[str, Field(default="")]
    current_atr: Annotated[Decimal, Field(...)]
    atr_history: Annotated[list[Decimal], Field(default_factory=list)]
    leverage: Annotated[int, Field(default=3, ge=1, le=125)]
    symbol_tier: Annotated[str, Field(default="TIER_2")]

    model_config = ConfigDict(frozen=True)
