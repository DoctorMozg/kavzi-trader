from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.date_window_schema import DateWindowSchema


class WalkForwardChoiceSchema(BaseModel):
    """The lookback picked for one test period, from data before it only."""

    model_config = ConfigDict(frozen=True)

    window: DateWindowSchema
    lookback: int
    # Net Sharpe of every candidate on the training days; None when undefined.
    scores: dict[int, float | None]
