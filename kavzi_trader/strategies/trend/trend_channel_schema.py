import numpy as np
from pydantic import BaseModel, ConfigDict


class TrendChannelSchema(BaseModel):
    """Donchian breakout levels per day, NaN until the lookback has filled."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    upper: np.ndarray
    lower: np.ndarray
