from enum import StrEnum
from typing import Literal

AnthropicEffort = Literal["low", "medium", "high", "xhigh", "max"]


class LlmProvider(StrEnum):
    """Where an LLM agent's requests are sent."""

    OPENROUTER = "openrouter"
    ANTHROPIC = "anthropic"
