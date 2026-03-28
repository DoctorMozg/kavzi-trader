from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class DeribitDvolDataSchema(BaseModel):
    """DVOL index and options market sentiment from Deribit."""

    dvol_index: Annotated[
        Decimal,
        Field(..., description="BTC DVOL implied volatility index"),
    ]
    btc_put_call_ratio: Annotated[
        Decimal,
        Field(..., description="BTC put/call open interest ratio"),
    ]
    eth_put_call_ratio: Annotated[
        Decimal | None,
        Field(default=None),
    ]
    fetched_at: Annotated[datetime, Field(...)]

    model_config = ConfigDict(frozen=True)


class FearGreedDataSchema(BaseModel):
    """Crypto Fear & Greed Index from Alternative.me."""

    value: Annotated[int, Field(..., ge=0, le=100)]
    classification: Annotated[
        str,
        Field(..., description="e.g. 'Fear', 'Greed', 'Extreme Fear'"),
    ]
    fetched_at: Annotated[datetime, Field(...)]

    model_config = ConfigDict(frozen=True)


class CryptoPanicDataSchema(BaseModel):
    """Aggregated news sentiment from CryptoPanic."""

    bullish_count: Annotated[int, Field(default=0)]
    bearish_count: Annotated[int, Field(default=0)]
    neutral_count: Annotated[int, Field(default=0)]
    top_headlines: Annotated[list[str], Field(default_factory=list)]
    sentiment_score: Annotated[
        Decimal,
        Field(
            ...,
            description="-1.0 (bearish) to +1.0 (bullish)",
        ),
    ]
    fetched_at: Annotated[datetime, Field(...)]

    model_config = ConfigDict(frozen=True)


class ExternalDataSnapshotSchema(BaseModel):
    """Aggregated snapshot of all external data sources.

    Each field is Optional because sources may be disabled or temporarily
    unavailable. Fed to the Sentiment Synthesizer for LLM analysis.
    """

    deribit_dvol: Annotated[DeribitDvolDataSchema | None, Field(default=None)]
    fear_greed: Annotated[FearGreedDataSchema | None, Field(default=None)]
    cryptopanic: Annotated[CryptoPanicDataSchema | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)

    def is_empty(self) -> bool:
        """Return True if all sources are unavailable."""
        return (
            self.deribit_dvol is None
            and self.fear_greed is None
            and self.cryptopanic is None
        )


class SentimentSummarySchema(BaseModel):
    """Pre-analyzed sentiment summary produced by the Sentiment Synthesizer.

    This compact summary is what flows into Analyst/Trader dependency
    schemas, saving tokens on expensive models.
    """

    summary: Annotated[
        str,
        Field(..., description="Compact LLM-generated analysis, ~2-3 sentences"),
    ]
    sentiment_bias: Annotated[
        Literal["BULLISH", "BEARISH", "NEUTRAL"],
        Field(...),
    ]
    confidence_adjustment: Annotated[
        Decimal,
        Field(
            ...,
            ge=Decimal("-0.10"),
            le=Decimal("0.10"),
            description="Suggested confidence adjustment for analyst/trader",
        ),
    ]
    generated_at: Annotated[datetime, Field(...)]

    model_config = ConfigDict(frozen=True)
