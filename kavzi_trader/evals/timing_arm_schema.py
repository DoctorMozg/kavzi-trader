from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

HOURS_PER_DAY = 24


class TimingArmSchema(BaseModel):
    """One way to move the trend rule off daily bars.

    A: the rule on bars of ``hours``, lookback counted in bars.
    B: the daily 20-day channel, checked at every ``hours`` bar close.
    """

    model_config = ConfigDict(frozen=True)

    approach: Literal["A", "B"]
    hours: Annotated[int, Field(ge=1, le=HOURS_PER_DAY)]

    @model_validator(mode="after")
    def _divides_the_day(self) -> Self:
        if HOURS_PER_DAY % self.hours:
            msg = f"bars of {self.hours}h do not divide a UTC day"
            raise ValueError(msg)
        return self

    @property
    def bars_per_day(self) -> int:
        return HOURS_PER_DAY // self.hours

    @property
    def label(self) -> str:
        return f"{self.approach}-{self.hours}h"


# Fixed by 2026_11_20_trend_timing.md; the Bonferroni family size is its length.
TIMING_ARMS = tuple(
    TimingArmSchema(approach=approach, hours=hours)
    for approach in ("A", "B")
    for hours in (12, 6, 4)
)
# The one arm 2026_11_21_trend_timing_holdout.md confirms on the holdout coins.
HOLDOUT_ARM = TimingArmSchema(approach="B", hours=6)
