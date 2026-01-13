from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RiskConfigSchema(BaseModel):
    risk_per_trade_percent: Decimal = Decimal("1.0")
    max_positions: int = 2
    min_rr_ratio: Decimal = Decimal("1.5")

    drawdown_pause_percent: Decimal = Decimal("3.0")
    drawdown_close_all_percent: Decimal = Decimal("5.0")

    min_sl_atr: Decimal = Decimal("0.5")
    max_sl_atr: Decimal = Decimal("3.0")

    volatility_low_threshold: Decimal = Decimal("-1.0")
    volatility_high_threshold: Decimal = Decimal("1.0")
    volatility_extreme_threshold: Decimal = Decimal("2.0")

    atr_zscore_period: int = 30

    model_config = ConfigDict(frozen=True)
