from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.position_sizer import PositionSizer
from kavzi_trader.spine.risk.schemas import (
    RiskValidationResultSchema,
    VolatilityRegime,
    VolatilityRegimeSchema,
)
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager


class DrawdownCheckResult(BaseModel):
    rejections: list[str]
    should_close_all: bool


class DynamicRiskValidator:
    def __init__(self, config: RiskConfigSchema | None = None) -> None:
        self._config = config or RiskConfigSchema()
        self._volatility_detector = VolatilityRegimeDetector(self._config)
        self._position_sizer = PositionSizer(self._config)
        self._exposure_limiter = ExposureLimiter(self._config)

    async def validate_trade(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        current_atr: Decimal,
        atr_history: list[Decimal],
        state_manager: StateManager,
    ) -> RiskValidationResultSchema:
        rejection_reasons: list[str] = []
        warnings: list[str] = []

        regime = self._volatility_detector.detect_regime(current_atr, atr_history)

        drawdown_result = await self._check_drawdown(state_manager)
        rejection_reasons.extend(drawdown_result.rejections)
        should_close_all = drawdown_result.should_close_all

        exposure_result = await self._check_exposure(symbol, state_manager)
        if exposure_result:
            rejection_reasons.append(exposure_result)

        regime_result = self._check_volatility_regime(regime)
        if regime_result:
            rejection_reasons.append(regime_result)

        sl_result = self._check_stop_loss(entry_price, stop_loss, current_atr, side)
        rejection_reasons.extend(sl_result)

        rr_result = self._check_risk_reward(entry_price, stop_loss, take_profit, side)
        if rr_result:
            rejection_reasons.append(rr_result)

        recommended_size = Decimal("0")
        if not rejection_reasons:
            account = await state_manager.get_account_state()
            if account:
                sl_distance = abs(entry_price - stop_loss)
                sl_atr_mult = (
                    sl_distance / current_atr if current_atr > 0 else Decimal("1")
                )
                size_result = self._position_sizer.calculate_size(
                    account_balance=account.total_balance_usdt,
                    atr=current_atr,
                    stop_loss_atr_multiplier=sl_atr_mult,
                    regime=regime,
                    entry_price=entry_price,
                )
                recommended_size = size_result.adjusted_size

        if regime.regime == VolatilityRegime.HIGH:
            warnings.append("HIGH volatility regime - position size reduced by 50%")

        return RiskValidationResultSchema(
            is_valid=len(rejection_reasons) == 0,
            rejection_reasons=rejection_reasons,
            volatility_regime=regime.regime,
            recommended_size=recommended_size,
            size_multiplier=regime.size_multiplier,
            warnings=warnings,
            should_close_all=should_close_all,
        )

    async def _check_drawdown(
        self,
        state_manager: StateManager,
    ) -> DrawdownCheckResult:
        rejections: list[str] = []
        should_close_all = False

        drawdown = await state_manager.get_current_drawdown()
        close_threshold = self._config.drawdown_close_all_percent
        pause_threshold = self._config.drawdown_pause_percent

        if drawdown >= close_threshold:
            msg = f"Drawdown {drawdown}% exceeds close-all ({close_threshold}%)"
            rejections.append(msg)
            should_close_all = True
        elif drawdown >= pause_threshold:
            rejections.append(
                f"Drawdown {drawdown}% exceeds pause threshold ({pause_threshold}%)",
            )

        return DrawdownCheckResult(
            rejections=rejections,
            should_close_all=should_close_all,
        )

    async def _check_exposure(
        self,
        symbol: str,
        state_manager: StateManager,
    ) -> str | None:
        positions = await state_manager.get_all_positions()
        exposure_check = self._exposure_limiter.check_exposure(symbol, positions)

        if not exposure_check.is_allowed:
            return exposure_check.rejection_reason
        return None

    def _check_volatility_regime(
        self,
        regime: VolatilityRegimeSchema,
    ) -> str | None:
        if regime.regime == VolatilityRegime.EXTREME:
            return f"EXTREME volatility (Z-score: {regime.atr_zscore}) - blocked"
        if regime.regime == VolatilityRegime.LOW:
            return f"LOW volatility (Z-score: {regime.atr_zscore}) - no movement"
        return None

    def _check_stop_loss(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        current_atr: Decimal,
        side: Literal["LONG", "SHORT"],
    ) -> list[str]:
        errors: list[str] = []

        if current_atr <= 0:
            return errors

        sl_distance = abs(entry_price - stop_loss)
        sl_atr_ratio = sl_distance / current_atr

        if side == "LONG" and stop_loss >= entry_price:
            errors.append("Stop loss must be below entry for LONG position")
        elif side == "SHORT" and stop_loss <= entry_price:
            errors.append("Stop loss must be above entry for SHORT position")

        min_sl = self._config.min_sl_atr
        max_sl = self._config.max_sl_atr

        if sl_atr_ratio < min_sl:
            errors.append(
                f"Stop loss too tight ({sl_atr_ratio:.2f} ATR, min: {min_sl})",
            )

        if sl_atr_ratio > max_sl:
            errors.append(f"Stop loss too wide ({sl_atr_ratio:.2f} ATR, max {max_sl})")

        return errors

    def _check_risk_reward(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        side: Literal["LONG", "SHORT"],
    ) -> str | None:
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)

        if risk == 0:
            return "Invalid stop loss distance (zero risk)"

        if side == "LONG" and take_profit <= entry_price:
            return "Take profit must be above entry for LONG position"
        if side == "SHORT" and take_profit >= entry_price:
            return "Take profit must be below entry for SHORT position"

        rr_ratio = reward / risk
        min_rr = self._config.min_rr_ratio

        if rr_ratio < min_rr:
            return f"R:R ratio {rr_ratio:.2f} below minimum {min_rr}"

        return None
