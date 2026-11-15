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
    label_shares: dict[str, float]
    base: dict[str, EdgeStatSchema]
    signals: list[SignalEdgeSchema]
    score_buckets: list[ScoreBucketSchema]

    model_config = ConfigDict(frozen=True)
