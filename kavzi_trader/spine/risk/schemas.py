from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class VolatilityRegime(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


REGIME_SIZE_MULTIPLIERS: dict[VolatilityRegime, Decimal] = {
    VolatilityRegime.LOW: Decimal(0),
    VolatilityRegime.NORMAL: Decimal("1.0"),
    VolatilityRegime.HIGH: Decimal("0.5"),
    VolatilityRegime.EXTREME: Decimal(0),
}

# TIER_1 symbols get reduced sizing in EXTREME instead of full block
_EXTREME_TIER1_MULTIPLIER = Decimal("0.25")


def get_regime_size_multiplier(
    regime: VolatilityRegime,
    symbol_tier: str = "TIER_2",
) -> Decimal:
    """Return position size multiplier considering both regime and tier.

    TIER_1 symbols trade at 25% size in EXTREME regime instead of being
    fully blocked, allowing high-liquidity assets to capture large moves.
    """
    if regime == VolatilityRegime.EXTREME and symbol_tier == "TIER_1":
        return _EXTREME_TIER1_MULTIPLIER
    return REGIME_SIZE_MULTIPLIERS[regime]


class VolatilityRegimeSchema(BaseModel):
    regime: VolatilityRegime
    atr_zscore: Decimal
    size_multiplier: Decimal
    is_tradeable: bool

    model_config = ConfigDict(frozen=True)


class PositionSizeResultSchema(BaseModel):
    base_size: Decimal
    adjusted_size: Decimal
    size_multiplier: Decimal
    risk_amount: Decimal

    model_config = ConfigDict(frozen=True)


class ExposureCheckSchema(BaseModel):
    is_allowed: bool
    current_position_count: int
    max_positions: int
    rejection_reason: str | None = None

    model_config = ConfigDict(frozen=True)


class RiskValidationResultSchema(BaseModel):
    is_valid: bool
    rejection_reasons: list[str]
    volatility_regime: VolatilityRegime
    recommended_size: Decimal
    size_multiplier: Decimal
    warnings: list[str]
    should_close_all: bool = False

    model_config = ConfigDict(frozen=True)
