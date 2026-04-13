from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kavzi_trader.commons.trading_constants import MIN_RR_RATIO

__all__ = ["MIN_RR_RATIO", "TradeDecisionSchema"]


class TradeDecisionSchema(BaseModel):
    """
    Final trading decision with entry, risk, and profit targets.

    This is the structured output used by the execution system to place
    or skip a trade.
    """

    action: Annotated[Literal["LONG", "SHORT", "WAIT", "CLOSE"], Field(...)]
    confidence: Annotated[float, Field(..., ge=0.0, le=1.0)]
    reasoning: Annotated[str, Field(..., min_length=40, max_length=600)]
    suggested_entry: Annotated[Decimal | None, Field(default=None)]
    suggested_stop_loss: Annotated[Decimal | None, Field(default=None)]
    suggested_take_profit: Annotated[Decimal | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_trade_logic(self) -> "TradeDecisionSchema":
        if self.action not in {"LONG", "SHORT"}:
            return self
        entry, stop, take = self._require_entry_stop_take()
        self._validate_price_ordering(entry, stop, take)
        self._validate_rr_ratio(entry, stop, take)
        return self

    def _require_entry_stop_take(self) -> tuple[Decimal, Decimal, Decimal]:
        if (
            self.suggested_entry is None
            or self.suggested_stop_loss is None
            or self.suggested_take_profit is None
        ):
            raise ValueError("Trade requires entry, stop loss, and take profit.")
        return (
            self.suggested_entry,
            self.suggested_stop_loss,
            self.suggested_take_profit,
        )

    def _validate_price_ordering(
        self, entry: Decimal, stop: Decimal, take: Decimal
    ) -> None:
        if self.action == "LONG" and not (stop < entry < take):
            raise ValueError("LONG requires stop < entry < take profit.")
        if self.action == "SHORT" and not (stop > entry > take):
            raise ValueError("SHORT requires stop > entry > take profit.")

    @staticmethod
    def _validate_rr_ratio(entry: Decimal, stop: Decimal, take: Decimal) -> None:
        risk = abs(entry - stop)
        if risk == 0:
            raise ValueError("Risk distance cannot be zero.")
        reward = abs(take - entry)
        if reward / risk < MIN_RR_RATIO:
            raise ValueError("Risk/reward ratio below minimum.")
