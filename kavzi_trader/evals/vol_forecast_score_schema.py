from pydantic import BaseModel, ConfigDict


class VolForecastScoreSchema(BaseModel):
    """Mean QLIKE of one forecaster and its Diebold-Mariano test against a baseline."""

    model_config = ConfigDict(frozen=True)

    name: str
    symbols: list[str]
    days: int
    mean_qlike: float
    baseline: str
    baseline_qlike: float
    # Positive when this forecaster loses less than the baseline.
    dm_stat: float | None
    # One-sided: probability of a gain this large if both forecast equally well.
    p_value: float | None
