from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_RR_RATIO = Decimal("1.5")


class TradeDecisionSchema(BaseModel):
    """
    Final trading decision with entry, risk, and profit targets.

    This is the structured output used by the execution system to place
    or skip a trade.
    """

    action: Annotated[Literal["LONG", "SHORT", "WAIT", "CLOSE"], Field(...)]
    confidence: Annotated[float, Field(..., ge=0.0, le=1.0)]
    reasoning: Annotated[str, Field(..., min_length=80, max_length=600)]
    suggested_entry: Annotated[Decimal | None, Field(default=None)]
    suggested_stop_loss: Annotated[Decimal | None, Field(default=None)]
    suggested_take_profit: Annotated[Decimal | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_trade_logic(self) -> "TradeDecisionSchema":
        if self.action in {"LONG", "SHORT"}:
            if (
                self.suggested_entry is None
                or self.suggested_stop_loss is None
                or self.suggested_take_profit is None
            ):
                raise ValueError("Trade requires entry, stop loss, and take profit.")
            if self.action == "LONG" and not (
                self.suggested_stop_loss
                < self.suggested_entry
                < self.suggested_take_profit
            ):
                raise ValueError("LONG requires stop < entry < take profit.")
            if self.action == "SHORT" and not (
                self.suggested_stop_loss
                > self.suggested_entry
                > self.suggested_take_profit
            ):
                raise ValueError("SHORT requires stop > entry > take profit.")
            risk = abs(self.suggested_entry - self.suggested_stop_loss)
            reward = abs(self.suggested_take_profit - self.suggested_entry)
            if risk == 0:
                raise ValueError("Risk distance cannot be zero.")
            if reward / risk < MIN_RR_RATIO:
                raise ValueError("Risk/reward ratio below minimum.")
        return self
