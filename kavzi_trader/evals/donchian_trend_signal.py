import numpy as np
import pandas as pd

from kavzi_trader.evals.trend_params_schema import TrendParamsSchema
from kavzi_trader.evals.trend_signal_schema import TrendSignalSchema

DAYS_PER_YEAR = 365


class DonchianTrendSignal:
    """Volatility-sized Donchian breakout ensemble on one symbol's daily closes.

    Value at index t depends only on closes[: t + 1], so it is known at close t.
    """

    def __init__(self, params: TrendParamsSchema) -> None:
        self._params = params

    def compute(self, close: np.ndarray, n_symbols: int) -> TrendSignalSchema:
        if n_symbols < 1:
            msg = f"n_symbols must be positive, got {n_symbols}"
            raise ValueError(msg)
        if close.ndim != 1:
            msg = f"close must be 1-D, got shape {close.shape}"
            raise ValueError(msg)
        states = np.array([self._state(close, lb) for lb in self._params.lookbacks])
        signal = states.mean(axis=0)
        scale = self._vol_scale(close)
        return TrendSignalSchema(signal=signal, weight=signal * scale / n_symbols)

    def _state(self, close: np.ndarray, lookback: int) -> np.ndarray:
        below = -1.0 if self._params.long_short else 0.0
        state = np.zeros(len(close))
        current = 0.0
        for t in range(lookback, len(close)):
            window = close[t - lookback : t]
            if close[t] > window.max():
                current = 1.0
            elif close[t] < window.min():
                current = below
            state[t] = current
        return state

    def _vol_scale(self, close: np.ndarray) -> np.ndarray:
        """min(target / vol, cap); zero while the vol window is still warming up."""
        log_ret = pd.Series(np.log(close)).diff()
        vol = log_ret.rolling(self._params.vol_window).std().to_numpy() * np.sqrt(
            DAYS_PER_YEAR
        )
        with np.errstate(divide="ignore"):
            scale = np.minimum(
                self._params.annual_vol_target / vol, self._params.max_leverage
            )
        capped: np.ndarray = np.nan_to_num(scale, nan=0.0)
        return capped
