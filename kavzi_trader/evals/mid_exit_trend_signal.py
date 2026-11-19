import numpy as np

from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema


class MidExitTrendSignal(DonchianTrendSignal):
    """Donchian long/flat that exits below the channel midpoint, not its low.

    Entry is unchanged: a close above the max of the previous ``lookback`` closes.
    The exit trails at the midpoint of that channel (Zarattini et al. 2025).
    """

    def __init__(self, params: TrendParamsSchema) -> None:
        if params.long_short:
            msg = "the midpoint exit is defined for long/flat only"
            raise ValueError(msg)
        super().__init__(params)

    def _state(self, close: np.ndarray, lookback: int) -> np.ndarray:
        state = np.zeros(len(close))
        current = 0.0
        for t in range(lookback, len(close)):
            window = close[t - lookback : t]
            high, low = window.max(), window.min()
            if close[t] > high:
                current = 1.0
            elif close[t] < (high + low) / 2:
                current = 0.0
            state[t] = current
        return state
