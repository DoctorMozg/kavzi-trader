from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DeribitDvolConfigSchema(BaseModel):
    """Configuration for Deribit DVOL + Put/Call Ratio source."""

    enabled: Annotated[bool, Field(default=True)]

    model_config = ConfigDict(frozen=True)


class FearGreedConfigSchema(BaseModel):
    """Configuration for Fear & Greed Index source."""

    enabled: Annotated[bool, Field(default=True)]

    model_config = ConfigDict(frozen=True)


class CryptoPanicConfigSchema(BaseModel):
    """Configuration for CryptoPanic news sentiment source."""

    enabled: Annotated[bool, Field(default=False)]
    max_results: Annotated[int, Field(default=20, ge=1, le=50)]
    max_headlines: Annotated[int, Field(default=5, ge=1, le=20)]

    model_config = ConfigDict(frozen=True)


class SynthesizerConfigSchema(BaseModel):
    """Configuration for the Sentiment Synthesizer LLM agent."""

    enabled: Annotated[bool, Field(default=True)]
    model_id: Annotated[str, Field(default="deepseek/deepseek-chat-v3-0324")]
    temperature: Annotated[float, Field(default=0.0, ge=0.0, le=2.0)]
    retries: Annotated[int, Field(default=1, ge=0, le=5)]

    model_config = ConfigDict(frozen=True)


class ExternalSourcesConfigSchema(BaseModel):
    """Top-level config for external data sources and sentiment synthesis."""

    enabled: Annotated[bool, Field(default=True)]
    run_interval_s: Annotated[int, Field(default=300, ge=30)]
    deribit_dvol: Annotated[
        DeribitDvolConfigSchema,
        Field(default_factory=DeribitDvolConfigSchema),
    ]
    fear_greed: Annotated[
        FearGreedConfigSchema,
        Field(default_factory=FearGreedConfigSchema),
    ]
    cryptopanic: Annotated[
        CryptoPanicConfigSchema,
        Field(default_factory=CryptoPanicConfigSchema),
    ]
    synthesizer: Annotated[
        SynthesizerConfigSchema,
        Field(default_factory=SynthesizerConfigSchema),
    ]

    model_config = ConfigDict(frozen=True)
