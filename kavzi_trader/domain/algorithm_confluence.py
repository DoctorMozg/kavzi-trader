from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ALGO_SIGNAL_COUNT = 8
MAX_DISCRETIONARY_POINTS = 3


class AlgorithmConfluenceSchema(BaseModel):
    """Summarizes rule-based confluence signals and their score."""

    ema_alignment: Annotated[bool, Field(...)]
    rsi_favorable: Annotated[bool, Field(...)]
    volume_above_average: Annotated[bool, Field(...)]
    price_at_bollinger: Annotated[bool, Field(...)]
    funding_favorable: Annotated[bool, Field(...)]
    oi_supports_direction: Annotated[bool, Field(...)]
    oi_funding_divergence: Annotated[bool, Field(...)]
    volume_spike: Annotated[bool, Field(...)]
    score: Annotated[int, Field(..., ge=0, le=ALGO_SIGNAL_COUNT)]
    # Signals whose inputs exist; the rest are scored False, not "bad".
    available_signals: Annotated[
        int, Field(default=ALGO_SIGNAL_COUNT, ge=0, le=ALGO_SIGNAL_COUNT)
    ]

    model_config = ConfigDict(frozen=True)


class DualConfluenceSchema(BaseModel):
    """Confluence scores for both LONG and SHORT directions."""

    long: Annotated[AlgorithmConfluenceSchema, Field(...)]
    short: Annotated[AlgorithmConfluenceSchema, Field(...)]
    detected_side: Annotated[Literal["LONG", "SHORT"], Field(...)]

    model_config = ConfigDict(frozen=True)

    @property
    def dominant(self) -> AlgorithmConfluenceSchema:
        """Higher-scoring side; LONG wins ties."""
        return self.long if self.long.score >= self.short.score else self.short
