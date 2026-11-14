import logging
from decimal import Decimal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from kavzi_trader.commons.trading_constants import MAX_TP_ATR
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.evals.market_feature_builder import REGIME_ORDER

logger = logging.getLogger(__name__)

# Midpoint of the 1.0-1.5 ATR stop range the Trader prompt gives for NORMAL
# (volatility_regimes.j2); LOW is told stops "may be tight", so it shares it.
_CALM_STOP_ATR = Decimal("1.25")
# The ATR_2X target style, the Trader prompt's default (trader.j2).
_BASE_TP_ATR = Decimal(2)


class BracketDistancesSchema(BaseModel):
    """Per-candidate SL/TP distances in price units; ``valid`` is False if rejected."""

    sl_distance: NDArray[np.float64]
    tp_distance: NDArray[np.float64]
    valid: NDArray[np.bool_]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class BracketPolicy:
    """The deterministic bracket the evals use, derived from the bot's geometry.

    The Trader LLM picks stop and target style itself, so there is no fixed
    multiple in the code. This policy fixes one per regime and applies the same
    floors, R:R extension and rejections as TradeGeometryCalculator (the builder
    cross-checks the sampled cases against that calculator).
    """

    def __init__(self, risk_config: RiskConfigSchema) -> None:
        self._risk = risk_config
        # Widest stop whose min-R:R target still fits under MAX_TP_ATR.
        stressed = MAX_TP_ATR / risk_config.min_rr_ratio
        self._stop_atr = {
            VolatilityRegime.LOW: _CALM_STOP_ATR,
            VolatilityRegime.NORMAL: _CALM_STOP_ATR,
            VolatilityRegime.HIGH: stressed,
            VolatilityRegime.EXTREME: stressed,
        }
        for regime, multiple in self._stop_atr.items():
            if not risk_config.min_sl_atr <= multiple <= risk_config.max_sl_atr:
                msg = f"stop multiple {multiple} for {regime} outside risk bounds"
                raise ValueError(msg)

    def nominal_stop_atr(self) -> dict[str, float]:
        return {r.value: float(m) for r, m in self._stop_atr.items()}

    def distances(
        self,
        regime_code: NDArray[np.int8],
        atr: NDArray[np.float64],
        price: NDArray[np.float64],
    ) -> BracketDistancesSchema:
        stop_atr = np.array(
            [float(self._stop_atr[r]) for r in REGIME_ORDER], dtype=np.float64
        )[regime_code]
        percent_floor = float(self._risk.min_sl_percent) / 100.0 * price
        sl = np.maximum(stop_atr * atr, percent_floor)
        required = float(self._risk.min_rr_ratio) * sl
        tp = np.maximum(float(_BASE_TP_ATR) * atr, required)
        valid = (sl <= float(self._risk.max_sl_atr) * atr) & (
            tp <= float(MAX_TP_ATR) * atr + 1e-12
        )
        return BracketDistancesSchema(sl_distance=sl, tp_distance=tp, valid=valid)
