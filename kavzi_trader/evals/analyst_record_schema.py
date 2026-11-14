from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema


class AnalystRecordSchema(BaseModel):
    """Analyst output for one case; the output fields are None without a decision."""

    setup_valid: bool | None = None
    direction: str | None = None
    confluence_score: int | None = None
    reasoning: str | None = None
    metrics: Annotated[StageMetricsSchema, Field(...)]

    model_config = ConfigDict(frozen=True)
