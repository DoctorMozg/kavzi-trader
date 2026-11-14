from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.token_usage_schema import TokenUsageSchema


class StageMetricsSchema(BaseModel):
    """Cost of one LLM stage for one case; zero requests means it never ran."""

    requests: Annotated[int, Field(ge=0)] = 0
    latency_ms: Annotated[float, Field(ge=0)] = 0.0
    usage: Annotated[TokenUsageSchema, Field(default_factory=TokenUsageSchema)]
    cost_usd: float | None = None
    # Exception class name of a failed request, e.g. ContentFilterError.
    error: str | None = None
    refusal: bool = False

    model_config = ConfigDict(frozen=True)
