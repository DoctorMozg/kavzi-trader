from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kavzi_trader.commons.trading_constants import MIN_RR_RATIO
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
    quantity: Annotated[Decimal | None, Field(default=None)]
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

    @model_validator(mode="after")
    def validate_trade_geometry(self) -> "DecisionMessageSchema":
        # Defense-in-depth: mirrors TradeDecisionSchema.validate_trade_logic so
        # malformed Trader output cannot construct an execution message even if
        # upstream guards are bypassed or refactored.
        if self.action == "CLOSE":
            return self
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("quantity must be positive when set")
        if self.action == "LONG" and not (
            self.stop_loss < self.entry_price < self.take_profit
        ):
            raise ValueError("LONG requires stop < entry < take_profit")
        if self.action == "SHORT" and not (
            self.stop_loss > self.entry_price > self.take_profit
        ):
            raise ValueError("SHORT requires stop > entry > take_profit")
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        if risk == 0:
            raise ValueError("risk distance cannot be zero")
        if reward / risk < MIN_RR_RATIO:
            raise ValueError("risk/reward ratio below minimum")
        return self
