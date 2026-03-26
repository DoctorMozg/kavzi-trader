from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AgentModelConfigSchema(BaseModel):
    """Configuration for a single LLM agent tier."""

    model_id: Annotated[str, Field(..., min_length=1)]
    retries: Annotated[int, Field(default=1, ge=0, le=5)]
    temperature: Annotated[float, Field(default=0.0, ge=0.0, le=2.0)]

    model_config = ConfigDict(frozen=True)


class BrainConfigSchema(BaseModel):
    """Configuration for the Brain (LLM) layer via OpenRouter."""

    openrouter_api_key: Annotated[str, Field(default="")]
    openrouter_base_url: Annotated[
        str, Field(default="https://openrouter.ai/api/v1")
    ]
    request_timeout_s: Annotated[
        float, Field(default=120.0, ge=5.0, le=600.0)
    ]
    scout: Annotated[
        AgentModelConfigSchema,
        Field(
            default_factory=lambda: AgentModelConfigSchema(
                model_id="qwen/qwen3.5-flash-02-23",
            ),
        ),
    ]
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

    model_config = ConfigDict(frozen=True)
