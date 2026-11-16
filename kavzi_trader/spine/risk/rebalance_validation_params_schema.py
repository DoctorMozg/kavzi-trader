from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RebalanceValidationParamsSchema(BaseModel):
    """Inputs for one DynamicRiskValidator.validate_rebalance call (long-only)."""

    symbol: str
    mark_price: Annotated[Decimal, Field(gt=0)]
    current_qty: Annotated[Decimal, Field(ge=0)]
    target_qty: Annotated[Decimal, Field(ge=0)]
    equity: Decimal
    leverage: Annotated[int, Field(ge=1)]
    disaster_stop_price: Decimal
    expires_at_ms: int
    now_ms: int

    model_config = ConfigDict(frozen=True)
