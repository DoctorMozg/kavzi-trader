import math
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.signal_bracket_schema import SignalBracketSchema


class EdgeStatSchema(BaseModel):
    """Mean R of taking one side on a group of bars, with a 95% interval."""

    n: Annotated[int, Field(ge=0)]
    mean_r: float | None
    # Half-width, widened for overlapping outcome windows; None below two bars.
    ci95: float | None
    win_rate: float | None

    model_config = ConfigDict(frozen=True)


class SignalEdgeSchema(BaseModel):
    side: str
    signal: str
    fired_share: Annotated[float, Field(ge=0, le=1)]
    fired: EdgeStatSchema
    not_fired: EdgeStatSchema

    model_config = ConfigDict(frozen=True)

    @property
    def lift(self) -> float | None:
        """Fired minus not-fired mean R: what the signal adds over market drift."""
        if self.fired.mean_r is None or self.not_fired.mean_r is None:
            return None
        return self.fired.mean_r - self.not_fired.mean_r

    @property
    def lift_ci95(self) -> float | None:
        if self.fired.ci95 is None or self.not_fired.ci95 is None:
            return None
        return math.hypot(self.fired.ci95, self.not_fired.ci95)


class ScoreBucketSchema(BaseModel):
    side: str
    bucket: str
    stat: EdgeStatSchema

    model_config = ConfigDict(frozen=True)


class BracketEdgeSchema(BaseModel):
    """Every signal's edge under one bracket."""

    bracket: SignalBracketSchema
    samples: Annotated[int, Field(ge=0)]
    ci_widening: Annotated[float, Field(ge=1)]
    mean_fee_r: Annotated[float, Field(ge=0)]
    label_shares: dict[str, float]
    base: dict[str, EdgeStatSchema]
    signals: list[SignalEdgeSchema]
    score_buckets: list[ScoreBucketSchema]

    model_config = ConfigDict(frozen=True)
