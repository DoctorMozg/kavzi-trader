from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class PositionManagementSchema(BaseModel):
    """
    Parameters that guide how an open trade should be managed over time.

    These settings tell the system when to move the stop loss, take partial
    profits, or exit if the trade is not progressing.
    """

    trailing_stop_atr_multiplier: Annotated[Decimal, Field(ge=Decimal("0.5"))]
    break_even_trigger_atr: Annotated[Decimal, Field(ge=Decimal("0.5"))]
    partial_exit_at_percent: Annotated[
        Decimal,
        Field(ge=Decimal("0.0"), le=Decimal("1.0")),
    ]
    partial_exit_size: Annotated[Decimal, Field(ge=Decimal("0.0"), le=Decimal("0.5"))]
    max_hold_time_hours: Annotated[int, Field(ge=1, le=168)]
    scale_in_allowed: Annotated[bool, Field(...)]
    scale_in_max_multiplier: Annotated[
        Decimal,
        Field(ge=Decimal("1.0"), le=Decimal("2.0")),
    ]

    model_config = ConfigDict(frozen=True)
