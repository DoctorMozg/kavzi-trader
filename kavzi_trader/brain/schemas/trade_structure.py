from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# The Trader agent's structural output vocabulary. Lives in the Brain layer
# because it is what the Trader emits; the Spine geometry calculator consumes
# it (spine -> brain, the established direction). Keeping these here avoids a
# brain.schemas.decision -> spine.execution import cycle.
EntryTactic = Literal["IMMEDIATE", "PULLBACK_TO_LEVEL"]
TargetStyle = Literal["STRUCTURAL", "ATR_2X", "ATR_3X"]
TradeDirection = Literal["LONG", "SHORT"]


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
