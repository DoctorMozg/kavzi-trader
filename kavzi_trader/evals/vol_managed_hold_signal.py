import numpy as np
import pandas as pd

from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema


class VolManagedHoldSignal:
    """Always long, sized exactly like the trend ensemble: isolates its vol scaling."""

    def __init__(self, params: TrendParamsSchema) -> None:
        self._sizer = DonchianTrendSignal(params)

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        n_symbols = closes.shape[1]
        return np.column_stack(
            [self._sizer.vol_scale(closes[s].to_numpy()) / n_symbols for s in closes]
        )
