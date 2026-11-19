from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.stop_fill_schema import StopFillSchema


class CrashReplayResultSchema(BaseModel):
    """One variant's book outcome over the replayed day, as a share of equity."""

    model_config = ConfigDict(frozen=True)

    name: str
    end_return: float
    # Worst mark-to-market book return at any minute, valuing longs at the low.
    worst_return: float
    worst_minute: str
    stops: list[StopFillSchema]
