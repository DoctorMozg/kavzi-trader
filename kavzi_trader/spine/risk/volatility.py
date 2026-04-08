import logging
from decimal import Decimal
from statistics import mean, stdev

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.schemas import (
    REGIME_SIZE_MULTIPLIERS,
    VolatilityRegime,
    VolatilityRegimeSchema,
)

logger = logging.getLogger(__name__)

MIN_HISTORY_LENGTH = 2


class VolatilityRegimeDetector:
    def __init__(self, config: RiskConfigSchema | None = None) -> None:
        self._config = config or RiskConfigSchema()

    def detect_regime(
        self,
        current_atr: Decimal,
        atr_history: list[Decimal],
    ) -> VolatilityRegimeSchema:
        if len(atr_history) < MIN_HISTORY_LENGTH:
            logger.warning(
                "ATR history has %d entries (need %d),"
                " zscore defaults to 0, regime may be unreliable",
                len(atr_history),
                MIN_HISTORY_LENGTH,
            )
        zscore = self._calculate_zscore(current_atr, atr_history)
        regime = self._classify_regime(zscore)
        multiplier = REGIME_SIZE_MULTIPLIERS[regime]
        logger.debug(
            "Volatility regime: regime=%s zscore=%s multiplier=%s",
            regime.value,
            zscore,
            multiplier,
        )

        return VolatilityRegimeSchema(
            regime=regime,
            atr_zscore=zscore,
            size_multiplier=multiplier,
            is_tradeable=regime != VolatilityRegime.LOW,
        )

    def _calculate_zscore(
        self,
        current_atr: Decimal,
        atr_history: list[Decimal],
    ) -> Decimal:
        if len(atr_history) < MIN_HISTORY_LENGTH:
            return Decimal(0)

        float_history = [float(atr) for atr in atr_history]
        avg = mean(float_history)
        std = stdev(float_history)

        if std == 0:
            return Decimal(0)

        zscore = (float(current_atr) - avg) / std
        return Decimal(str(round(zscore, 4)))

    def _classify_regime(self, zscore: Decimal) -> VolatilityRegime:
        if zscore < self._config.volatility_low_threshold:
            return VolatilityRegime.LOW
        if zscore > self._config.volatility_extreme_threshold:
            return VolatilityRegime.EXTREME
        if zscore > self._config.volatility_high_threshold:
            return VolatilityRegime.HIGH
        return VolatilityRegime.NORMAL
