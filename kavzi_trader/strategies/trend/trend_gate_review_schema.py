from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from kavzi_trader.domain.trend_gate_decision import TrendGateDecisionSchema


class TrendGateReviewSchema(BaseModel):
    """The gate's verdict on one entry, with everything needed to audit it."""

    symbol: str
    as_of: AwareDatetime
    decision: Literal["KEEP", "VETO"]
    samples: list[TrendGateDecisionSchema]
    coin_headlines: int
    other_headlines: int
    prompt_sha: str
    shadow: bool = True

    model_config = ConfigDict(frozen=True)
