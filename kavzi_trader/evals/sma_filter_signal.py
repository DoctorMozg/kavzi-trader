import numpy as np
import pandas as pd

MIN_WINDOW = 2


class SmaFilterSignal:
    """Unlevered long while the close is above its simple moving average, else flat."""

    def __init__(self, window: int) -> None:
        if window < MIN_WINDOW:
            msg = f"window must be at least {MIN_WINDOW}, got {window}"
            raise ValueError(msg)
        self._window = window

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        # The average includes day t's close, so the weight is known at close t.
        average = closes.rolling(self._window).mean()
        above: np.ndarray = (closes > average).to_numpy(dtype=float)
        weights: np.ndarray = above / closes.shape[1]
        return weights
