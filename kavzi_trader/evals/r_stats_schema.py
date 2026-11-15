from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.confusion_metrics import ratio


class RStatsSchema(BaseModel):
    """Trade count, win rate and R totals of a list of R multiples."""

    trades: Annotated[int, Field(ge=0)]
    win_rate: float | None
    mean_r: float | None
    total_r: float

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_r(cls, values: list[float]) -> RStatsSchema:
        total = sum(values)
        return cls(
            trades=len(values),
            win_rate=ratio(sum(v > 0 for v in values), len(values)),
            mean_r=ratio(total, len(values)),
            total_r=total,
        )
