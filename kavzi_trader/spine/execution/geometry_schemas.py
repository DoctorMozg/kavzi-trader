from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.brain.schemas.analyst import KeyLevelSchema

EntryTactic = Literal["IMMEDIATE", "PULLBACK_TO_LEVEL"]
TargetStyle = Literal["STRUCTURAL", "ATR_2X", "ATR_3X"]
TradeDirection = Literal["LONG", "SHORT"]
GeometryRejectionCode = Literal[
    "NO_ATR",
    "INVALID_STRUCTURE",
    "SL_TOO_WIDE",
    "SL_BEYOND_LIQUIDATION",
    "TP_UNREACHABLE",
]


class GeometryInputsSchema(BaseModel):
    """Market context required to turn a trade structure into prices."""

    symbol: Annotated[str, Field(...)]
    current_price: Annotated[Decimal, Field(..., gt=0)]
    atr_14: Annotated[Decimal | None, Field(default=None)]
    key_levels: Annotated[list[KeyLevelSchema], Field(default_factory=list)]
    leverage: Annotated[int, Field(default=1, ge=1, le=125)]

    model_config = ConfigDict(frozen=True)


class TradeStructureSchema(BaseModel):
    """
    Structural trade choices made by the Trader agent.

    The agent never emits prices; it selects which structure anchors the
    trade and the Spine derives exact entry / stop / target prices from it.
    Exactly one stop anchor must be provided: a key-level index or an ATR
    multiplier.
    """

    direction: Annotated[TradeDirection, Field(...)]
    entry_tactic: Annotated[EntryTactic, Field(default="IMMEDIATE")]
    entry_level_index: Annotated[int | None, Field(default=None, ge=0)]
    stop_level_index: Annotated[int | None, Field(default=None, ge=0)]
    stop_atr_multiplier: Annotated[Decimal | None, Field(default=None, gt=0)]
    target_style: Annotated[TargetStyle, Field(...)]

    model_config = ConfigDict(frozen=True)


class TradeGeometrySchema(BaseModel):
    """Concrete prices computed from a ``TradeStructureSchema``."""

    entry: Annotated[Decimal, Field(..., gt=0)]
    stop_loss: Annotated[Decimal, Field(..., gt=0)]
    take_profit: Annotated[Decimal, Field(..., gt=0)]
    rr_ratio: Annotated[Decimal, Field(..., gt=0)]
    sl_atr_multiple: Annotated[Decimal, Field(..., gt=0)]
    adjustments: Annotated[list[str], Field(default_factory=list)]

    model_config = ConfigDict(frozen=True)


class GeometryRejectionSchema(BaseModel):
    """Typed refusal to derive geometry, with an operator-readable detail."""

    code: Annotated[GeometryRejectionCode, Field(...)]
    detail: Annotated[str, Field(...)]

    model_config = ConfigDict(frozen=True)


class GeometryViabilitySchema(BaseModel):
    """Cheap pre-LLM answer to "could any legal geometry reach min R:R?"."""

    viable: Annotated[bool, Field(...)]
    best_rr: Annotated[Decimal | None, Field(default=None)]
    reason: Annotated[str | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)
