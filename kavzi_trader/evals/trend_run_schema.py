import numpy as np
from pydantic import BaseModel, ConfigDict


class TrendRunSchema(BaseModel):
    """Daily portfolio accounting; row t is the return day after weights are set."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    gross: np.ndarray
    cost: np.ndarray
    funding: np.ndarray
    net: np.ndarray
    traded: np.ndarray
