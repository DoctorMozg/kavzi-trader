import numpy as np
from pydantic import BaseModel, ConfigDict


class TrendSignalSchema(BaseModel):
    """Per-day signal and target weight, both indexed like the input closes."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    signal: np.ndarray
    weight: np.ndarray
