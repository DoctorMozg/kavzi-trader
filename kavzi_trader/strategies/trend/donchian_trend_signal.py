import numpy as np
import pandas as pd

from kavzi_trader.strategies.trend.trend_channel_schema import TrendChannelSchema
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.trend_signal_schema import TrendSignalSchema

DAYS_PER_YEAR = 365


class DonchianTrendSignal:
    """Volatility-sized Donchian breakout ensemble on one symbol's daily closes.

    Value at index t depends only on closes[: t + 1], so it is known at close t.
    """

    def __init__(self, params: TrendParamsSchema) -> None:
        self._params = params

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        """Target weights (days, symbols), the book split evenly across columns."""
        n_symbols = closes.shape[1]
        return np.column_stack(
            [self.compute(closes[s].to_numpy(), n_symbols).weight for s in closes]
        )

    def compute(self, close: np.ndarray, n_symbols: int) -> TrendSignalSchema:
        if n_symbols < 1:
            msg = f"n_symbols must be positive, got {n_symbols}"
            raise ValueError(msg)
        if close.ndim != 1:
            msg = f"close must be 1-D, got shape {close.shape}"
            raise ValueError(msg)
        states = np.array([self._state(close, lb) for lb in self._params.lookbacks])
        signal = states.mean(axis=0)
        scale = self.vol_scale(close)
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

    def annual_vol(self, close: np.ndarray) -> np.ndarray:
        """Rolling annualised vol of daily log returns; NaN while warming up."""
        log_ret = pd.Series(np.log(close)).diff()
        vol: np.ndarray = log_ret.rolling(
            self._params.vol_window
        ).std().to_numpy() * np.sqrt(DAYS_PER_YEAR)
        return vol

    @staticmethod
    def channel(close: np.ndarray, lookback: int) -> TrendChannelSchema:
        """Max and min of the previous `lookback` closes: the levels close[t] breaks."""
        prior = pd.Series(close).shift(1).rolling(lookback)
        return TrendChannelSchema(
            upper=prior.max().to_numpy(), lower=prior.min().to_numpy()
        )

    def vol_scale(self, close: np.ndarray) -> np.ndarray:
        """min(target / vol, cap); zero while the vol window is still warming up."""
        vol = self.annual_vol(close)
        with np.errstate(divide="ignore"):
            scale = np.minimum(
                self._params.annual_vol_target / vol, self._params.max_leverage
            )
        capped: np.ndarray = np.nan_to_num(scale, nan=0.0)
        return capped
