from pydantic import BaseModel, ConfigDict


class PairedSharpeSchema(BaseModel):
    """Sharpe of an arm minus its base over the same days, with a bootstrap interval."""

    model_config = ConfigDict(frozen=True)

    base_sharpe: float
    arm_sharpe: float
    difference: float
    # Two-sided interval of the difference at ``confidence``; 90% is the 5th and 95th
    # bootstrap percentiles.
    lower: float
    upper: float
    # Share of bootstrap differences at or below zero.
    p_not_better: float
    resamples: int
    mean_block_days: int
    confidence: float = 0.90
