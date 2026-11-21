from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.bar_quality_schema import BarQualitySchema
from kavzi_trader.evals.timing_arm_outcome_schema import TimingArmOutcomeSchema
from kavzi_trader.evals.timing_result_schema import TimingResultSchema


class TimingRunSchema(BaseModel):
    """The base and the six arms on one universe, with the checks that void a run."""

    model_config = ConfigDict(frozen=True)

    universe: str
    base: TimingResultSchema
    arms: list[TimingArmOutcomeSchema]
    quality: list[BarQualitySchema]
    reproduction_error: str | None
    quality_error: str | None
