import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict


class TimingInputsSchema(BaseModel):
    """Per bar interval: weights held, return per unit of day-start notional, funding.

    ``checkpoints`` are the bar closes where each row's weights were set; ``days``
    are the UTC days whose return the row belongs to.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    checkpoints: pd.DatetimeIndex
    days: pd.DatetimeIndex
    held: np.ndarray
    returns: np.ndarray
    funding: np.ndarray
