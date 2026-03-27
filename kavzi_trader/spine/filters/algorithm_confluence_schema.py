from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class AlgorithmConfluenceSchema(BaseModel):
    """Summarizes rule-based confluence signals and their score."""

    ema_alignment: Annotated[bool, Field(...)]
    rsi_favorable: Annotated[bool, Field(...)]
    volume_above_average: Annotated[bool, Field(...)]
    price_at_bollinger: Annotated[bool, Field(...)]
    funding_favorable: Annotated[bool, Field(...)]
    oi_supports_direction: Annotated[bool, Field(...)]
    volume_spike: Annotated[bool, Field(...)]
    score: Annotated[int, Field(..., ge=0, le=7)]

    model_config = ConfigDict(frozen=True)


class DualConfluenceSchema(BaseModel):
    """Confluence scores for both LONG and SHORT directions."""

    long: Annotated[AlgorithmConfluenceSchema, Field(...)]
    short: Annotated[AlgorithmConfluenceSchema, Field(...)]
    detected_side: Annotated[Literal["LONG", "SHORT"], Field(...)]

    model_config = ConfigDict(frozen=True)
