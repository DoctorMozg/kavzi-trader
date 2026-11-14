from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kavzi_trader.commons.llm_provider import AnthropicEffort, LlmProvider

_DEFAULT_OPENROUTER_SYNTH_MODEL = "deepseek/deepseek-chat-v3-0324"


class DeribitDvolConfigSchema(BaseModel):
    """Configuration for Deribit DVOL + Put/Call Ratio source."""

    enabled: Annotated[bool, Field(default=True)]

    model_config = ConfigDict(frozen=True)


class FearGreedConfigSchema(BaseModel):
    """Configuration for Fear & Greed Index source."""

    enabled: Annotated[bool, Field(default=True)]

    model_config = ConfigDict(frozen=True)


class CCDataNewsConfigSchema(BaseModel):
    """Configuration for CCData news sentiment source (no API key required)."""

    enabled: Annotated[bool, Field(default=True)]
    max_results: Annotated[int, Field(default=20, ge=1, le=50)]
    max_headlines: Annotated[int, Field(default=5, ge=1, le=20)]

    model_config = ConfigDict(frozen=True)


class SynthesizerConfigSchema(BaseModel):
    """Configuration for the Sentiment Synthesizer LLM agent."""

    enabled: Annotated[bool, Field(default=True)]
    provider: Annotated[LlmProvider, Field(default=LlmProvider.OPENROUTER)]
    # None with Anthropic means the factory's default synthesizer model.
    model_id: Annotated[str | None, Field(default=None, min_length=1)]
    # Anthropic only; None means the factory's default synthesizer effort.
    effort: Annotated[AnthropicEffort | None, Field(default=None)]
    temperature: Annotated[float, Field(default=0.0, ge=0.0, le=2.0)]
    retries: Annotated[int, Field(default=1, ge=0, le=5)]
    seed: Annotated[int | None, Field(default=42)]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _default_openrouter_model(cls, data: object) -> object:
        if not isinstance(data, dict) or data.get("model_id") is not None:
            return data
        provider = LlmProvider(data.get("provider", LlmProvider.OPENROUTER))
        if provider is LlmProvider.OPENROUTER:
            return {**data, "model_id": _DEFAULT_OPENROUTER_SYNTH_MODEL}
        return data


class CircuitBreakerConfigSchema(BaseModel):
    """Configuration for per-source circuit breaker."""

    failure_threshold: Annotated[int, Field(default=5, ge=1)] = 5
    cooldown_s: Annotated[int, Field(default=900, ge=60)] = 900
    max_cooldown_s: Annotated[int, Field(default=3600, ge=300)] = 3600
    max_reopen_count: Annotated[int, Field(default=3, ge=1)] = 3

    model_config = ConfigDict(frozen=True)


class ExternalSourcesConfigSchema(BaseModel):
    """Top-level config for external data sources and sentiment synthesis."""

    enabled: Annotated[bool, Field(default=True)]
    run_interval_s: Annotated[int, Field(default=300, ge=30)]
    circuit_breaker: Annotated[
        CircuitBreakerConfigSchema,
        Field(default_factory=CircuitBreakerConfigSchema),
    ]
    deribit_dvol: Annotated[
        DeribitDvolConfigSchema,
        Field(default_factory=DeribitDvolConfigSchema),
    ]
    fear_greed: Annotated[
        FearGreedConfigSchema,
        Field(default_factory=FearGreedConfigSchema),
    ]
    ccdata_news: Annotated[
        CCDataNewsConfigSchema,
        Field(default_factory=CCDataNewsConfigSchema),
    ]
    synthesizer: Annotated[
        SynthesizerConfigSchema,
        Field(default_factory=SynthesizerConfigSchema),
    ]

    model_config = ConfigDict(frozen=True)
