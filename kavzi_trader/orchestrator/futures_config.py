from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class FuturesConfigSchema(BaseModel):
    """Configuration for USDT-M perpetual futures trading."""

    default_leverage: Annotated[int, Field(default=5, ge=1, le=125)]
    margin_type: Annotated[str, Field(default="ISOLATED")]
    symbol_leverage: Annotated[dict[str, int], Field(default_factory=dict)]
    liquidation_emergency_percent: Annotated[Decimal, Field(default=Decimal("5.0"))]

    model_config = ConfigDict(frozen=True)
