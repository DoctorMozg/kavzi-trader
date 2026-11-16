from typing import Protocol

import numpy as np
import pandas as pd


class WeightSignal(Protocol):
    """Target weights per day and symbol, each known at that day's close."""

    def weights(self, closes: pd.DataFrame) -> np.ndarray: ...
