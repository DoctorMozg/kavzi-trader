import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict


class ScoredInputsSchema(BaseModel):
    """Per return day: held weights, close-to-close returns and funding to pay."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    days: pd.DatetimeIndex
    held: np.ndarray
    returns: np.ndarray
    funding: np.ndarray
    # Returns with NaN kept where a symbol was not traded, for the benchmark.
    raw_returns: np.ndarray
