from datetime import date

from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.walk_forward_choice_schema import WalkForwardChoiceSchema


class WalkForwardResultSchema(BaseModel):
    """Per-period choices and the stitched out-of-sample backtest."""

    model_config = ConfigDict(frozen=True)

    train_first_day: date
    choices: list[WalkForwardChoiceSchema]
    out_of_sample: TrendResultSchema
