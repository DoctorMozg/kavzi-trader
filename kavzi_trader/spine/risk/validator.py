import logging
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.position_sizer import PositionSizer
from kavzi_trader.spine.risk.schemas import (
    RiskValidationResultSchema,
    VolatilityRegime,
    VolatilityRegimeSchema,
)
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class DrawdownCheckResult(BaseModel):
    rejections: list[str]
    should_close_all: bool

    model_config = ConfigDict(frozen=True)


class DynamicRiskValidator:
    def __init__(
        self,
        config: RiskConfigSchema | None = None,
        tier_registry: SymbolTierRegistry | None = None,
    ) -> None:
        self._config = config or RiskConfigSchema()
        self._tier_registry = tier_registry
        self._volatility_detector = VolatilityRegimeDetector(self._config)
        self._position_sizer = PositionSizer(self._config, tier_registry)
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
        leverage: int = 1,
        confidence: Decimal | None = None,
        symbol_tier: str = "TIER_2",
    ) -> RiskValidationResultSchema:
        rejection_reasons: list[str] = []
        warnings: list[str] = []

        logger.info(
            "Risk validation started: symbol=%s side=%s entry=%s SL=%s TP=%s ATR=%s",
            symbol,
            side,
            entry_price,
            stop_loss,
            take_profit,
            current_atr,
            extra={"symbol": symbol, "side": side},
        )

        if current_atr <= 0:
            logger.warning(
                "ATR is %s for %s, SL validation will be skipped",
                current_atr,
                symbol,
            )

        regime = self._volatility_detector.detect_regime(current_atr, atr_history)

        drawdown_result = await self._check_drawdown(state_manager)
        rejection_reasons.extend(drawdown_result.rejections)
        should_close_all = drawdown_result.should_close_all
        logger.debug(
            "Drawdown check: rejections=%d should_close_all=%s",
            len(drawdown_result.rejections),
            should_close_all,
        )
        if should_close_all:
            logger.warning(
                "Emergency drawdown for %s — should_close_all=True",
                symbol,
            )

        exposure_result = await self._check_exposure(symbol, state_manager)
        if exposure_result:
            rejection_reasons.append(exposure_result)
        logger.debug("Exposure check: result=%s", exposure_result)

        regime_result = self._check_volatility_regime(regime, symbol_tier)
        if regime_result:
            rejection_reasons.append(regime_result)
        logger.debug(
            "Regime check: regime=%s result=%s",
            regime.regime.value,
            regime_result,
        )

        sl_result = self._check_stop_loss(entry_price, stop_loss, current_atr, side)
        rejection_reasons.extend(sl_result)
        logger.debug("SL check: rejections=%s", sl_result)

        rr_result = self._check_risk_reward(entry_price, stop_loss, take_profit, side)
        if rr_result:
            rejection_reasons.append(rr_result)
        logger.debug("R:R check: result=%s", rr_result)

        liq_result = self._check_liquidation_distance(
            entry_price,
            stop_loss,
            side,
            leverage,
        )
        if liq_result:
            rejection_reasons.append(liq_result)
        logger.debug("Liquidation check: result=%s", liq_result)

        margin_result = await self._check_margin_ratio(state_manager)
        if margin_result:
            rejection_reasons.append(margin_result)
        logger.debug("Margin ratio check: result=%s", margin_result)

        confidence_result = self._check_tier_confidence(symbol, confidence)
        if confidence_result:
            rejection_reasons.append(confidence_result)
        logger.debug("Tier confidence check: result=%s", confidence_result)

        recommended_size = Decimal(0)
        if not rejection_reasons:
            account = await state_manager.get_account_state()
            if account:
                sl_distance = abs(entry_price - stop_loss)
                sl_atr_mult = (
                    sl_distance / current_atr if current_atr > 0 else Decimal(1)
                )
                size_result = self._position_sizer.calculate_size(
                    account_balance=account.total_balance_usdt,
                    available_balance=account.available_balance_usdt,
                    atr=current_atr,
                    stop_loss_atr_multiplier=sl_atr_mult,
                    regime=regime,
                    entry_price=entry_price,
                    leverage=leverage,
                    symbol=symbol,
                )
                recommended_size = size_result.adjusted_size
                logger.debug(
                    "Position sizing: balance=%s base=%s adjusted=%s multiplier=%s",
                    account.total_balance_usdt,
                    size_result.base_size,
                    size_result.adjusted_size,
                    size_result.size_multiplier,
                )
            else:
                logger.warning(
                    "Account state unavailable, cannot size position for %s",
                    symbol,
                )

        if regime.regime == VolatilityRegime.HIGH:
            warnings.append("HIGH volatility regime - position size reduced by 50%")

        logger.info(
            "Risk validation result: symbol=%s valid=%s rejections=%d"
            " size=%s regime=%s",
            symbol,
            len(rejection_reasons) == 0,
            len(rejection_reasons),
            recommended_size,
            regime.regime.value,
            extra={"symbol": symbol},
        )
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
        try:
            drawdown = await state_manager.get_current_drawdown()
        except Exception:
            logger.exception(
                "Failed to check drawdown, rejecting trade as safety measure",
            )
            return DrawdownCheckResult(
                rejections=["Drawdown check failed — state unavailable"],
                should_close_all=False,
            )

        rejections: list[str] = []
        should_close_all = False
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
        try:
            positions = await state_manager.get_all_positions()
        except Exception:
            logger.exception(
                "Failed to check exposure for %s, rejecting as safety measure",
                symbol,
            )
            return "Exposure check failed — state unavailable"
        exposure_check = self._exposure_limiter.check_exposure(symbol, positions)

        if not exposure_check.is_allowed:
            return exposure_check.rejection_reason
        return None

    def _check_volatility_regime(
        self,
        regime: VolatilityRegimeSchema,
        symbol_tier: str = "TIER_2",
    ) -> str | None:
        if regime.regime == VolatilityRegime.EXTREME:
            if symbol_tier == "TIER_1":
                return None  # TIER_1 allowed through EXTREME with reduced sizing
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

        if entry_price > 0:
            sl_pct = (sl_distance / entry_price) * 100
            if sl_pct < self._config.min_sl_percent:
                errors.append(
                    f"Stop loss too tight"
                    f" ({sl_pct:.3f}%, min: {self._config.min_sl_percent}%)",
                )

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

    def _check_liquidation_distance(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        side: Literal["LONG", "SHORT"],
        leverage: int,
    ) -> str | None:
        if leverage <= 1:
            return None

        if side == "LONG":
            liq_price = entry_price * (Decimal(1) - Decimal(1) / Decimal(leverage))
        else:
            liq_price = entry_price * (Decimal(1) + Decimal(1) / Decimal(leverage))

        # SL must fire before forced liquidation
        if side == "LONG" and stop_loss <= liq_price:
            return (
                f"Stop loss at or beyond liquidation price "
                f"(SL: {stop_loss:.2f}, liq: {liq_price:.2f}, "
                f"leverage: {leverage}x)"
            )
        if side == "SHORT" and stop_loss >= liq_price:
            return (
                f"Stop loss at or beyond liquidation price "
                f"(SL: {stop_loss:.2f}, liq: {liq_price:.2f}, "
                f"leverage: {leverage}x)"
            )

        # SL must maintain a safety margin from liquidation price
        liq_distance = abs(entry_price - liq_price)
        buffer = liq_distance * self._config.liquidation_sl_buffer_ratio

        if side == "LONG" and stop_loss < liq_price + buffer:
            return (
                f"Stop loss too close to liquidation price "
                f"(SL: {stop_loss:.2f}, min: {liq_price + buffer:.2f}, "
                f"leverage: {leverage}x)"
            )
        if side == "SHORT" and stop_loss > liq_price - buffer:
            return (
                f"Stop loss too close to liquidation price "
                f"(SL: {stop_loss:.2f}, max: {liq_price - buffer:.2f}, "
                f"leverage: {leverage}x)"
            )

        return None

    def _check_tier_confidence(
        self,
        symbol: str,
        confidence: Decimal | None,
    ) -> str | None:
        if self._tier_registry is None or confidence is None:
            return None
        tier_config = self._tier_registry.get_config(symbol)
        if confidence < tier_config.min_confidence:
            tier = self._tier_registry.get_tier(symbol)
            return (
                f"Confidence {confidence:.2f} below tier minimum "
                f"{tier_config.min_confidence} ({tier.value})"
            )
        return None

    async def _check_margin_ratio(
        self,
        state_manager: StateManager,
    ) -> str | None:
        try:
            account = await state_manager.get_account_state()
        except Exception:
            logger.exception(
                "Failed to check margin ratio, rejecting as safety measure",
            )
            return "Margin ratio check failed — state unavailable"

        if account is None:
            return None

        max_ratio = self._config.max_margin_ratio
        if account.margin_ratio >= max_ratio:
            return (
                f"Account margin ratio {account.margin_ratio:.2f} "
                f"exceeds maximum {max_ratio}"
            )

        return None
