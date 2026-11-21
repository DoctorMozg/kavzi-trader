from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.timing_arm_schema import TimingArmSchema
from kavzi_trader.evals.timing_result_schema import TimingResultSchema
from kavzi_trader.evals.validation.paired_sharpe_schema import PairedSharpeSchema


class TimingArmOutcomeSchema(BaseModel):
    """An arm's result and its paired comparison with the base at two levels."""

    model_config = ConfigDict(frozen=True)

    arm: TimingArmSchema
    scored: TimingResultSchema
    paired: PairedSharpeSchema
    adjusted: PairedSharpeSchema
