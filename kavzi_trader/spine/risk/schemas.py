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
