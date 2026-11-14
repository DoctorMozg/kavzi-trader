import logging

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.evals.market_features_schema import MarketFeaturesSchema

logger = logging.getLogger(__name__)

REGIME_ORDER = (
    VolatilityRegime.LOW,
    VolatilityRegime.NORMAL,
    VolatilityRegime.HIGH,
    VolatilityRegime.EXTREME,
)
_ATR_PERIOD = 14
# Mirrors MarketDataCache.ATR_HISTORY_WINDOW; a test keeps them equal.
ATR_HISTORY_WINDOW = 30
_ZSCORE_DECIMALS = 4


class MarketFeatureBuilder:
    """Vectorised ATR and volatility regime that mirror the live bot's.

    ATR is Wilder-smoothed like indicators.volatility.calculate_atr; the regime
    is the ATR z-score over the last ATR_HISTORY_WINDOW ATRs, classified with the
    risk-config thresholds exactly as VolatilityRegimeDetector does.
    """

    def __init__(self, risk_config: RiskConfigSchema) -> None:
        self._low = float(risk_config.volatility_low_threshold)
        self._high = float(risk_config.volatility_high_threshold)
        self._extreme = float(risk_config.volatility_extreme_threshold)

    def build(self, frame: pd.DataFrame) -> MarketFeaturesSchema:
        high = frame["high"].to_numpy(dtype=np.float64)
        low = frame["low"].to_numpy(dtype=np.float64)
        close = frame["close"].to_numpy(dtype=np.float64)
        atr = self._wilder_atr(high, low, close)
        zscore = self._zscore(atr)
        return MarketFeaturesSchema(
            atr=atr, atr_zscore=zscore, regime_code=self._classify(zscore)
        )

    @staticmethod
    def _wilder_atr(
        high: NDArray[np.float64],
        low: NDArray[np.float64],
        close: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        atr = np.full(len(close), np.nan)
        if len(close) <= _ATR_PERIOD:
            return atr
        prev_close = np.concatenate(([np.nan], close[:-1]))
        true_range = np.fmax.reduce(
            [high - low, np.abs(high - prev_close), np.abs(low - prev_close)]
        )
        alpha = 1.0 / _ATR_PERIOD
        atr[_ATR_PERIOD - 1] = true_range[:_ATR_PERIOD].mean()
        for i in range(_ATR_PERIOD, len(close)):
            atr[i] = atr[i - 1] * (1 - alpha) + true_range[i] * alpha
        return atr

    @staticmethod
    def _zscore(atr: NDArray[np.float64]) -> NDArray[np.float64]:
        series = pd.Series(atr)
        rolling = series.rolling(ATR_HISTORY_WINDOW)
        std = rolling.std().to_numpy()
        z = (atr - rolling.mean().to_numpy()) / std
        # The detector reports zero when the ATR history is flat.
        z = np.where(std == 0, 0.0, z)
        return np.round(z, _ZSCORE_DECIMALS)

    def _classify(self, zscore: NDArray[np.float64]) -> NDArray[np.int8]:
        code = np.select(
            [zscore < self._low, zscore > self._extreme, zscore > self._high],
            [
                REGIME_ORDER.index(VolatilityRegime.LOW),
                REGIME_ORDER.index(VolatilityRegime.EXTREME),
                REGIME_ORDER.index(VolatilityRegime.HIGH),
            ],
            default=REGIME_ORDER.index(VolatilityRegime.NORMAL),
        )
        return code.astype(np.int8)
