from decimal import Decimal
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kavzi_trader.brain.schemas.trade_structure import (
    EntryTactic,
    TargetStyle,
    TradeDirection,
    TradeStructureSchema,
)

__all__ = ["TradeDecisionSchema"]


class TradeDecisionSchema(BaseModel):
    """
    Final trading decision expressed as structure, not prices.

    The Trader agent picks which structure anchors the trade — entry tactic,
    stop anchor (a key-level index or an ATR multiplier), and target style.
    The Spine's ``TradeGeometryCalculator`` derives the exact entry /
    stop-loss / take-profit prices and enforces the minimum risk:reward
    ratio deterministically, so the model never performs price arithmetic.
    """

    action: Annotated[Literal["LONG", "SHORT", "WAIT", "CLOSE"], Field(...)]
    confidence: Annotated[float, Field(..., ge=0.0, le=1.0)]
    reasoning: Annotated[str, Field(..., min_length=40, max_length=600)]
    entry_tactic: Annotated[EntryTactic | None, Field(default=None)]
    entry_level_index: Annotated[int | None, Field(default=None, ge=0)]
    stop_level_index: Annotated[int | None, Field(default=None, ge=0)]
    stop_atr_multiplier: Annotated[Decimal | None, Field(default=None, gt=0)]
    target_style: Annotated[TargetStyle | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _default_entry_tactic(cls, data: object) -> object:
        # IMMEDIATE is the unambiguous default; tolerating its omission
        # avoids burning an LLM retry on a missing-but-inferable field.
        if isinstance(data, dict) and data.get("action") in {"LONG", "SHORT"}:
            data.setdefault("entry_tactic", "IMMEDIATE")
        return data

    @model_validator(mode="after")
    def validate_trade_structure(self) -> "TradeDecisionSchema":
        if self.action not in {"LONG", "SHORT"}:
            return self
        if self.target_style is None:
            raise ValueError("LONG/SHORT requires target_style.")
        has_level_stop = self.stop_level_index is not None
        has_atr_stop = self.stop_atr_multiplier is not None
        if has_level_stop == has_atr_stop:
            raise ValueError(
                "LONG/SHORT requires exactly one stop anchor:"
                " stop_level_index or stop_atr_multiplier."
            )
        if self.entry_tactic == "PULLBACK_TO_LEVEL" and self.entry_level_index is None:
            raise ValueError("PULLBACK_TO_LEVEL requires entry_level_index.")
        return self

    def to_structure(self) -> TradeStructureSchema:
        """Convert an actionable decision into geometry-calculator input."""
        if self.action not in {"LONG", "SHORT"} or self.target_style is None:
            raise ValueError(f"No trade structure for action {self.action}.")
        return TradeStructureSchema(
            direction=cast("TradeDirection", self.action),
            entry_tactic=self.entry_tactic or "IMMEDIATE",
            entry_level_index=self.entry_level_index,
            stop_level_index=self.stop_level_index,
            stop_atr_multiplier=self.stop_atr_multiplier,
            target_style=self.target_style,
        )
