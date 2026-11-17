from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from kavzi_trader.commons.llm_provider import AnthropicEffort, LlmProvider


class AgentModelConfigSchema(BaseModel):
    """Configuration for a single LLM agent tier."""

    provider: Annotated[LlmProvider, Field(default=LlmProvider.OPENROUTER)]
    # None is only valid for Anthropic, where the factory picks the per-agent default.
    model_id: Annotated[str | None, Field(default=None, min_length=1)]
    # Anthropic only; None means the factory's per-agent default effort.
    effort: Annotated[AnthropicEffort | None, Field(default=None)]
    retries: Annotated[int, Field(default=3, ge=0, le=5)]
    temperature: Annotated[float, Field(default=0.0, ge=0.0, le=2.0)]
    # None means "inherit request_timeout_s from the parent BrainConfig".
    # A non-None value overrides the global timeout for this tier; use a
    # large value (e.g. 300) to approximate "no timeout" instead of 0.
    timeout_s: Annotated[float | None, Field(default=None, ge=0.0, le=300.0)]
    seed: Annotated[int | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _openrouter_needs_model_id(self) -> AgentModelConfigSchema:
        if self.provider is LlmProvider.OPENROUTER and self.model_id is None:
            msg = "model_id is required when provider is openrouter"
            raise ValueError(msg)
        return self


class BrainConfigSchema(BaseModel):
    """Configuration for the Brain (LLM) layer (OpenRouter and/or Anthropic)."""

    openrouter_api_key: Annotated[SecretStr, Field(default=SecretStr(""))]
    anthropic_api_key: Annotated[SecretStr, Field(default=SecretStr(""))]
    openrouter_base_url: Annotated[
        str,
        Field(default="https://openrouter.ai/api/v1"),
    ]
    request_timeout_s: Annotated[
        float,
        Field(default=120.0, ge=5.0, le=600.0),
    ]
    # SDK-level retries of 429/5xx for the direct Anthropic client. Each retry
    # can burn a full timeout_s, so keep it low against the Analyst budget.
    anthropic_max_retries: Annotated[int, Field(default=2, ge=0, le=5)]
    analyst: Annotated[
        AgentModelConfigSchema,
        Field(
            default_factory=lambda: AgentModelConfigSchema(
                model_id="openai/gpt-5",
            ),
        ),
    ]
    trader: Annotated[
        AgentModelConfigSchema,
        Field(
            default_factory=lambda: AgentModelConfigSchema(
                model_id="anthropic/claude-opus-4.6",
            ),
        ),
    ]
    # Shadow news check on trend entries (strategy.trend_following.gate).
    gate: Annotated[
        AgentModelConfigSchema,
        Field(
            default_factory=lambda: AgentModelConfigSchema(
                provider=LlmProvider.ANTHROPIC
            ),
        ),
    ]
    # Hard cap on concurrent Analyst LLM calls launched from a single
    # ReasoningLoop cycle. Prevents OpenRouter burst saturation when many
    # symbols escalate at once. Session 2026-04-14 observed 54% Analyst
    # failure rate without this guard.
    analyst_concurrency_limit: Annotated[int, Field(default=3, ge=1, le=16)]

    model_config = ConfigDict(frozen=True)

    def api_key_for(self, provider: LlmProvider) -> SecretStr:
        if provider is LlmProvider.ANTHROPIC:
            return self.anthropic_api_key
        return self.openrouter_api_key


class AnthropicAgentDefaultsSchema(BaseModel):
    """Model and effort an agent gets on Anthropic when none is configured."""

    model_id: Annotated[str, Field(min_length=1)]
    effort: AnthropicEffort

    model_config = ConfigDict(frozen=True)


# Thinking counts toward this. Eval p99 was ~2.1k (Analyst) and <1k (Trader);
# staying under ~21k also keeps requests unstreamed, so timeout_s bounds them.
ANTHROPIC_MAX_OUTPUT_TOKENS = 8192

ANTHROPIC_AGENT_DEFAULTS: dict[str, AnthropicAgentDefaultsSchema] = {
    "analyst": AnthropicAgentDefaultsSchema(
        model_id="claude-sonnet-5-5", effort="medium"
    ),
    "trader": AnthropicAgentDefaultsSchema(model_id="claude-opus-5-5", effort="medium"),
    "synthesizer": AnthropicAgentDefaultsSchema(
        model_id="claude-sonnet-5-5", effort="low"
    ),
    "gate": AnthropicAgentDefaultsSchema(model_id="claude-sonnet-5-5", effort="medium"),
}
