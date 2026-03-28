from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.spine.position.position_action_type import PositionActionType


class PositionActionSchema(BaseModel):
    """Explains what change should happen to an open position."""

    action: Annotated[PositionActionType, Field(...)]
    new_stop_loss: Annotated[Decimal | None, Field(default=None)] = None
    exit_quantity: Annotated[Decimal | None, Field(default=None)] = None
    reason: Annotated[str, Field(...)]

    model_config = ConfigDict(frozen=True)
