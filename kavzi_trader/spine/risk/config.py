from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class RiskConfigSchema(BaseModel):
    risk_per_trade_percent: Decimal = Decimal("1.0")
    max_positions: int = 2
    min_rr_ratio: Decimal = Decimal("2.0")

    drawdown_pause_percent: Decimal = Decimal("3.0")
    drawdown_close_all_percent: Decimal = Decimal("5.0")

    min_sl_atr: Decimal = Decimal("0.5")
    max_sl_atr: Decimal = Decimal("3.0")
    min_sl_percent: Decimal = Decimal("0.15")

    volatility_low_threshold: Decimal = Decimal("-1.5")
    volatility_high_threshold: Decimal = Decimal("1.0")
    volatility_extreme_threshold: Decimal = Decimal("2.0")

    atr_zscore_period: int = 30

    max_notional_percent: Decimal = Decimal("50.0")

    # Minimum position notional (in USDT) the sizer will emit.
    # Risk-based sizing can produce tiny positions on small accounts that fall
    # below Binance's per-symbol MIN_NOTIONAL filter. The sizer bumps below-floor
    # sizes up to this value; if the max-notional cap or margin capacity cannot
    # honour the floor, the validator rejects the trade outright.
    min_position_notional_usd: Decimal = Decimal("10.0")

    liquidation_emergency_percent: Decimal = Decimal("5.0")
    liquidation_sl_buffer_ratio: Decimal = Decimal("0.20")
    max_margin_ratio: Decimal = Decimal("0.5")

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> Self:
        if self.drawdown_pause_percent >= self.drawdown_close_all_percent:
            msg = "drawdown_pause_percent must be < drawdown_close_all_percent"
            raise ValueError(msg)
        if self.min_sl_atr >= self.max_sl_atr:
            msg = "min_sl_atr must be < max_sl_atr"
            raise ValueError(msg)
        if not (
            self.volatility_low_threshold
            < self.volatility_high_threshold
            < self.volatility_extreme_threshold
        ):
            msg = "volatility thresholds must be ordered: low < high < extreme"
            raise ValueError(msg)
        if self.min_position_notional_usd < 0:
            msg = "min_position_notional_usd must be >= 0"
            raise ValueError(msg)
        return self
