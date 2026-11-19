import numpy as np
from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.stop_fill_schema import StopFillSchema


class SymbolReplaySchema(BaseModel):
    """One symbol's replayed day per unit of weight."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # Worst mark-to-market return at each minute, valuing the position at the low.
    path: np.ndarray
    end_return: float
    stop: StopFillSchema | None
