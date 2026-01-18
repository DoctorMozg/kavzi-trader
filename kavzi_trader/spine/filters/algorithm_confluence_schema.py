from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AlgorithmConfluenceSchema(BaseModel):
    """Summarizes rule-based confluence signals and their score."""

    ema_alignment: Annotated[bool, Field(...)]
    rsi_favorable: Annotated[bool, Field(...)]
    volume_above_average: Annotated[bool, Field(...)]
    price_at_bollinger: Annotated[bool, Field(...)]
    funding_favorable: Annotated[bool, Field(...)]
    oi_supports_direction: Annotated[bool, Field(...)]
    score: Annotated[int, Field(..., ge=0, le=6)]

    model_config = ConfigDict(frozen=True)
