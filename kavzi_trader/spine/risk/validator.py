import logging
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.risk.position_sizer import PositionSizer
from kavzi_trader.spine.risk.rebalance_validation_params_schema import (
    RebalanceValidationParamsSchema,
)
from kavzi_trader.spine.risk.schemas import (
    RiskValidationResultSchema,
    VolatilityRegimeSchema,
)
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from kavzi_trader.spine.risk.trade_validation_params_schema import (
    TradeValidationParamsSchema,
)
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class DrawdownCheckResultSchema(BaseModel):
    rejections: list[str]
    should_close_all: bool

    model_config = ConfigDict(frozen=True)


class DynamicRiskValidator:
    def __init__(
        self,
        config: RiskConfigSchema | None = None,
        tier_registry: SymbolTierRegistry | None = None,
        liquidation_calculator: LiquidationCalculator | None = None,
        precision: SymbolPrecision | None = None,
    ) -> None:
        self._config = config or RiskConfigSchema()
        self._tier_registry = tier_registry
        self._precision = precision
        self._volatility_detector = VolatilityRegimeDetector(self._config)
        self._position_sizer = PositionSizer(self._config, tier_registry, precision)
        self._exposure_limiter = ExposureLimiter(self._config)
        self._liquidation_calculator = liquidation_calculator

    async def validate_trade(
        self,
        params: TradeValidationParamsSchema,
        state_manager: StateManager,
    ) -> RiskValidationResultSchema:
        symbol = params.symbol
        side = params.side
        entry_price = params.entry_price
        stop_loss = params.stop_loss
        take_profit = params.take_profit
        current_atr = params.current_atr
        atr_history = params.atr_history
        leverage = params.leverage
        confidence = params.confidence
        symbol_tier = params.symbol_tier
        size_multiplier = params.size_multiplier
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
                "ATR is %s for %s, trade will be rejected",
                current_atr,
                symbol,
            )

        regime = self._volatility_detector.detect_regime(
            current_atr,
            atr_history,
            symbol_tier,
            confidence,
        )

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

        portfolio_risk_result = await self._check_total_portfolio_risk(
            symbol,
            state_manager,
        )
        if portfolio_risk_result:
            rejection_reasons.append(portfolio_risk_result)
        logger.debug("Portfolio risk check: result=%s", portfolio_risk_result)

        regime_result = self._check_volatility_regime(regime)
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

        margin_result = await self._check_margin_ratio(state_manager)
        if margin_result:
            rejection_reasons.append(margin_result)
        logger.debug("Margin ratio check: result=%s", margin_result)

        confidence_result = self._check_tier_confidence(symbol, confidence)
        if confidence_result:
            rejection_reasons.append(confidence_result)
        logger.debug("Tier confidence check: result=%s", confidence_result)

        # Sizing runs even after earlier rejections: the liquidation bracket
        # needs the real quantity, and its reason should be reported alongside
        # the others. Floor rejections stay exclusive to otherwise-clean trades.
        sizing_rejections: list[str] = []
        recommended_size = await self._compute_recommended_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            current_atr=current_atr,
            regime=regime,
            leverage=leverage,
            state_manager=state_manager,
            rejection_reasons=sizing_rejections,
            filter_size_multiplier=size_multiplier,
        )
        if not rejection_reasons:
            rejection_reasons.extend(sizing_rejections)

        liq_result = await self._check_liquidation_distance(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            side=side,
            leverage=leverage,
            quantity=recommended_size,
        )
        if liq_result:
            rejection_reasons.append(liq_result)
        logger.debug("Liquidation check: result=%s", liq_result)

        if rejection_reasons:
            recommended_size = Decimal(0)

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

    @property
    def min_position_notional_usd(self) -> Decimal:
        return self._config.min_position_notional_usd

    async def validate_rebalance(
        self,
        params: RebalanceValidationParamsSchema,
        state_manager: StateManager,
    ) -> list[str]:
        """Shared checks for a target-weight resize; empty list means accepted.

        Max-positions is deliberately not checked: a resize is not a new
        position, and the book size is the strategy's own choice.
        """
        reasons: list[str] = []
        if params.now_ms > params.expires_at_ms:
            reasons.append(
                f"Intent expired {params.now_ms - params.expires_at_ms}ms ago",
            )
        # Reducing exposure must stay possible while paused or over a cap.
        if params.target_qty <= params.current_qty:
            return reasons

        reasons.extend((await self._check_drawdown(state_manager)).rejections)
        margin_result = await self._check_margin_ratio(state_manager)
        if margin_result:
            reasons.append(margin_result)

        target_notional = params.target_qty * params.mark_price
        max_percent = self._position_sizer.max_exposure_percent(params.symbol)
        max_notional = params.equity * max_percent / 100
        if target_notional > max_notional:
            reasons.append(
                f"Target notional {target_notional:.2f} exceeds cap "
                f"{max_notional:.2f} ({max_percent}% of equity)",
            )

        liq_result = await self._check_liquidation_distance(
            symbol=params.symbol,
            entry_price=params.mark_price,
            stop_loss=params.disaster_stop_price,
            side="LONG",
            leverage=params.leverage,
            quantity=params.target_qty,
        )
        if liq_result:
            reasons.append(liq_result)
        return reasons

    async def _compute_recommended_size(
        self,
        symbol: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        current_atr: Decimal,
        regime: VolatilityRegimeSchema,
        leverage: int,
        state_manager: StateManager,
        rejection_reasons: list[str],
        filter_size_multiplier: Decimal,
    ) -> Decimal:
        try:
            account = await state_manager.get_account_state()
        except Exception:
            # Sizing now runs after earlier rejections too, which may be
            # caused by this very outage; the margin check already reports it.
            logger.exception(
                "Failed to load account state for sizing %s",
                symbol,
                extra={"symbol": symbol, "check": "sizing"},
            )
            return Decimal(0)
        if account is None:
            logger.warning(
                "Account state unavailable, cannot size position for %s",
                symbol,
            )
            return Decimal(0)

        sl_distance = abs(entry_price - stop_loss)
        sl_atr_mult = sl_distance / current_atr if current_atr > 0 else Decimal(1)
        size_result = self._position_sizer.calculate_size(
            account_balance=account.total_balance_usdt,
            available_balance=account.available_balance_usdt,
            atr=current_atr,
            stop_loss_atr_multiplier=sl_atr_mult,
            regime=regime,
            entry_price=entry_price,
            leverage=leverage,
            symbol=symbol,
            filter_size_multiplier=filter_size_multiplier,
        )
        recommended_size = size_result.adjusted_size
        logger.debug(
            "Position sizing: balance=%s base=%s adjusted=%s multiplier=%s",
            account.total_balance_usdt,
            size_result.base_size,
            size_result.adjusted_size,
            size_result.size_multiplier,
        )

        # Reject when the final size is still under the notional floor.
        # The sizer already tried to bump it up; if a downstream clamp
        # (max-notional cap or margin capacity) brought it back below the
        # floor, the account cannot afford a viable position.
        min_notional_floor = self._config.min_position_notional_usd
        if min_notional_floor > 0 and recommended_size > 0:
            final_notional = recommended_size * entry_price
            if final_notional < min_notional_floor:
                rejection_reasons.append(
                    f"Position notional ${final_notional:.2f} below "
                    f"minimum ${min_notional_floor} (filter size multiplier "
                    f"{filter_size_multiplier}) — account cannot "
                    f"afford a floor-sized trade",
                )
                return Decimal(0)

        if self._precision is not None and recommended_size > 0:
            reason = self._precision.check_qty(symbol, recommended_size, entry_price)
            if reason is not None:
                rejection_reasons.append(f"Position size not tradable: {reason}")
                return Decimal(0)

        return recommended_size

    async def _check_drawdown(
        self,
        state_manager: StateManager,
    ) -> DrawdownCheckResultSchema:
        try:
            drawdown = await state_manager.get_current_drawdown()
        except Exception:
            logger.exception(
                "Failed to check drawdown, rejecting trade as safety measure",
                extra={"reason": "risk_validation_error", "check": "drawdown"},
            )
            return DrawdownCheckResultSchema(
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

        return DrawdownCheckResultSchema(
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
                extra={
                    "symbol": symbol,
                    "reason": "risk_validation_error",
                    "check": "exposure",
                },
            )
            return "Exposure check failed — state unavailable"
        exposure_check = self._exposure_limiter.check_exposure(symbol, positions)

        if not exposure_check.is_allowed:
            return exposure_check.rejection_reason
        return None

    async def _check_total_portfolio_risk(
        self,
        symbol: str,
        state_manager: StateManager,
    ) -> str | None:
        # Per-position notional caps and the max-position count don't bound the
        # *aggregate* loss two correlated positions can take in a single candle.
        # Two TIER_1 positions at 4% each = 8% concurrent open risk, which can
        # blow through the drawdown pause and close-all thresholds in one move
        # before either fires. Cap the summed risk just under the pause level.
        if self._tier_registry is None:
            return None

        try:
            positions = await state_manager.get_all_positions()
        except Exception:
            logger.exception(
                "Failed to check portfolio risk for %s, rejecting as safety measure",
                symbol,
                extra={
                    "symbol": symbol,
                    "reason": "risk_validation_error",
                    "check": "portfolio_risk",
                },
            )
            return "Portfolio risk check failed — state unavailable"

        max_portfolio_risk_percent = self._config.drawdown_pause_percent - Decimal(
            "0.5"
        )
        open_risk = sum(
            (
                self._tier_registry.get_config(pos.symbol).risk_per_trade_percent
                for pos in positions
            ),
            Decimal(0),
        )
        new_trade_risk = self._tier_registry.get_config(symbol).risk_per_trade_percent
        total_risk = open_risk + new_trade_risk

        if total_risk > max_portfolio_risk_percent:
            return (
                f"Portfolio risk {total_risk}% exceeds cap "
                f"({max_portfolio_risk_percent}%)"
            )
        return None

    def _check_volatility_regime(
        self,
        regime: VolatilityRegimeSchema,
    ) -> str | None:
        if regime.regime == VolatilityRegime.EXTREME:
            # The detector already folded tier and confidence override into the
            # multiplier, so zero here means the policy blocks this trade.
            if regime.size_multiplier <= 0:
                return f"EXTREME volatility (Z-score: {regime.atr_zscore}) - blocked"
            logger.info(
                "EXTREME regime allowed at reduced size: multiplier=%s",
                regime.size_multiplier,
            )
            return None
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

        if side == "LONG" and stop_loss >= entry_price:
            errors.append("Stop loss must be below entry for LONG position")
        elif side == "SHORT" and stop_loss <= entry_price:
            errors.append("Stop loss must be above entry for SHORT position")

        if current_atr <= 0:
            errors.append(f"ATR unavailable ({current_atr}), cannot validate stop loss")
            return errors

        sl_distance = abs(entry_price - stop_loss)
        sl_atr_ratio = sl_distance / current_atr

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

    async def _check_liquidation_distance(
        self,
        symbol: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        side: Literal["LONG", "SHORT"],
        leverage: int,
        quantity: Decimal,
    ) -> str | None:
        # Zero quantity means nothing will be opened (no account state, floor
        # or sizer zero), so there is no notional to bracket.
        if leverage <= 1 or quantity <= 0:
            return None

        if self._liquidation_calculator is None:
            # Without a calibrated MMR source the naive formula silently
            # over-estimates liq distance and would wave through stop losses
            # that sit beyond the real liquidation. Rejecting here forces
            # callers to wire a LiquidationCalculator for leveraged trades.
            logger.warning(
                "No liquidation calculator configured for %s at %sx leverage; "
                "rejecting trade as safety measure",
                symbol,
                leverage,
            )
            return (
                f"Liquidation check unavailable "
                f"(no MMR source for leverage {leverage}x)"
            )

        # MMR brackets are keyed on position notional, not per-unit price.
        notional = quantity * entry_price
        liq_price = await self._liquidation_calculator.estimate_liquidation_price(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            leverage=leverage,
            notional=notional,
        )
        if liq_price is None:
            logger.warning(
                "Could not compute liquidation price for %s, rejecting trade "
                "as safety measure",
                symbol,
            )
            return (
                f"Liquidation price unavailable for {symbol}; "
                f"cannot verify stop-loss safety"
            )

        logger.debug(
            "Liquidation distance check %s side=%s entry=%s liq=%s SL=%s",
            symbol,
            side,
            entry_price,
            liq_price,
            stop_loss,
        )

        # SL must fire before forced liquidation
        sl_past_liq = (
            stop_loss <= liq_price if side == "LONG" else stop_loss >= liq_price
        )
        if sl_past_liq:
            return (
                f"Stop loss at or beyond liquidation price "
                f"(SL: {stop_loss:.2f}, liq: {liq_price:.2f}, "
                f"leverage: {leverage}x)"
            )

        # SL must maintain a safety margin from liquidation price
        liq_distance = abs(entry_price - liq_price)
        buffer = liq_distance * self._config.liquidation_sl_buffer_ratio
        if side == "LONG":
            safe_threshold = liq_price + buffer
            too_close = stop_loss < safe_threshold
            bound_label = "min"
        else:
            safe_threshold = liq_price - buffer
            too_close = stop_loss > safe_threshold
            bound_label = "max"

        if too_close:
            return (
                f"Stop loss too close to liquidation price "
                f"(SL: {stop_loss:.2f}, {bound_label}: {safe_threshold:.2f}, "
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
                extra={"reason": "risk_validation_error", "check": "margin_ratio"},
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
