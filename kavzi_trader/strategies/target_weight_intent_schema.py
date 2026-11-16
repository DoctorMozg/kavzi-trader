from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class TargetWeightIntentSchema(BaseModel):
    """Absolute target for one symbol as a fraction of equity (long or flat)."""

    kind: Annotated[Literal["target_weight"], Field()] = "target_weight"
    strategy: Annotated[str, Field(min_length=1)]
    intent_id: Annotated[str, Field(min_length=1)]
    symbol: Annotated[str, Field(min_length=1)]
    target_weight: Annotated[Decimal, Field(ge=0)]
    # Wide protective stop as a fraction of entry price; the strategy exits on signal.
    disaster_stop_pct: Annotated[Decimal, Field(gt=0, lt=1)]
    created_at_ms: Annotated[int, Field(ge=0)]
    expires_at_ms: Annotated[int, Field(ge=0)]
    reason: Annotated[str, Field()] = ""

    model_config = ConfigDict(frozen=True)
