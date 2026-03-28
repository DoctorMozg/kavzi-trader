from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class SymbolTier(StrEnum):
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"


class SymbolTierConfigSchema(BaseModel):
    risk_per_trade_percent: Annotated[
        Decimal,
        Field(description="Max risk per trade as % of balance"),
    ]
    max_leverage: Annotated[
        int,
        Field(ge=1, description="Maximum allowed leverage"),
    ]
    max_exposure_percent: Annotated[
        Decimal,
        Field(description="Max notional exposure as % of balance"),
    ]
    min_confidence: Annotated[
        Decimal,
        Field(
            ge=Decimal("0"),
            le=Decimal("1"),
            description="Minimum LLM confidence to enter a trade",
        ),
    ]
    crowded_long_zscore: Annotated[
        Decimal,
        Field(description="Funding z-score above which longs are crowded"),
    ]
    crowded_short_zscore: Annotated[
        Decimal,
        Field(description="Funding z-score below which shorts are crowded"),
    ]

    model_config = ConfigDict(frozen=True)
