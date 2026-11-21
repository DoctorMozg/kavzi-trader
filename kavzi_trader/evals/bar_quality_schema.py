from pydantic import BaseModel, ConfigDict


class BarQualitySchema(BaseModel):
    """How well the 1h-derived bars agree with the daily closes they sit under."""

    model_config = ConfigDict(frozen=True)

    hours: int
    listed_days: int
    # Intraday bars missing on listed days; the previous close is carried over.
    gap_bars: int
    # Listed days whose last bar close is missing or differs from the daily close.
    day_end_mismatches: int
    max_day_end_gap: float

    @property
    def mismatch_share(self) -> float:
        return self.day_end_mismatches / self.listed_days if self.listed_days else 0.0
