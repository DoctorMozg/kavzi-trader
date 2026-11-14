from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from kavzi_trader.domain.volatility_regime import VolatilityRegime


class VolatilityRegimeSchema(BaseModel):
    regime: VolatilityRegime
    atr_zscore: Decimal
    size_multiplier: Decimal

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
