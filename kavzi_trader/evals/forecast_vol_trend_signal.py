import numpy as np
import pandas as pd

from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema


class ForecastVolTrendSignal:
    """The Donchian rule sized by a variance forecast instead of trailing vol.

    Weight = signal x min(target / forecast vol, cap) / N; no forecast, no position.
    """

    def __init__(self, params: TrendParamsSchema, variance: pd.DataFrame) -> None:
        self._params = params
        self._rule = DonchianTrendSignal(params)
        self._variance = variance

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        n_symbols = closes.shape[1]
        variance = self._variance.reindex(index=closes.index, columns=closes.columns)
        vol = np.sqrt(variance.to_numpy())
        with np.errstate(divide="ignore", invalid="ignore"):
            scale = np.minimum(
                self._params.annual_vol_target / vol, self._params.max_leverage
            )
        scale = np.nan_to_num(scale, nan=0.0)
        signal = np.column_stack(
            [self._rule.compute(closes[s].to_numpy(), n_symbols).signal for s in closes]
        )
        weights: np.ndarray = signal * scale / n_symbols
        return weights
