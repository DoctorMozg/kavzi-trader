import logging
from decimal import Decimal
from typing import Literal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.correlation import CorrelationFilter
from kavzi_trader.spine.filters.fear_greed_gate import FearGreedGateFilter
from kavzi_trader.spine.filters.filter_chain_result_schema import (
    FilterChainResultSchema,
)
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema
from kavzi_trader.spine.filters.funding import FundingRateFilter
from kavzi_trader.spine.filters.liquidity import LiquidityFilter
from kavzi_trader.spine.filters.movement import MinimumMovementFilter
from kavzi_trader.spine.filters.spike_cooldown import SpikeCooldownFilter
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.schemas import get_regime_size_multiplier
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class PreTradeFilterChain:
    """Runs ordered pre-trade checks and returns a unified decision."""

    def __init__(
        self,
        volatility_detector: VolatilityRegimeDetector,
        funding_filter: FundingRateFilter,
        movement_filter: MinimumMovementFilter,
        exposure_limiter: ExposureLimiter,
        liquidity_filter: LiquidityFilter,
        correlation_filter: CorrelationFilter,
        confluence_calculator: ConfluenceCalculator,
        fear_greed_gate: FearGreedGateFilter | None = None,
        spike_cooldown_filter: SpikeCooldownFilter | None = None,
        config: FilterConfigSchema | None = None,
    ) -> None:
        self._volatility_detector = volatility_detector
        self._funding_filter = funding_filter
        self._movement_filter = movement_filter
        self._exposure_limiter = exposure_limiter
        self._liquidity_filter = liquidity_filter
        self._correlation_filter = correlation_filter
        self._confluence_calculator = confluence_calculator
        self._fear_greed_gate = fear_greed_gate
        self._spike_cooldown_filter = spike_cooldown_filter
        self._config = config or FilterConfigSchema()

    async def evaluate(  # noqa: PLR0911, PLR0912
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        candle: CandlestickSchema,
        indicators: TechnicalIndicatorsSchema,
        order_flow: OrderFlowSchema | None,
        positions: list[PositionSchema],
        atr_history: list[Decimal],
        analyst_confluence_score: int | None = None,
        symbol_tier: str = "TIER_2",
    ) -> FilterChainResultSchema:
        results: list[FilterResultSchema] = []
        size_multiplier = Decimal("1.0")
        logger.info(
            "Filter chain started for %s %s",
            symbol,
            side,
            extra={"symbol": symbol, "side": side},
        )

        # --- FGI extreme gate (market-wide circuit breaker) ---
        if self._fear_greed_gate is not None:
            fgi_result = self._fear_greed_gate.evaluate()
            results.append(fgi_result)
            if not fgi_result.is_allowed:
                fgi_bypass = self._config.fgi_fear_bypass_confluence_min
                if (
                    analyst_confluence_score is not None
                    and analyst_confluence_score >= fgi_bypass
                ):
                    fgi_mult = self._config.fgi_fear_bypass_size_multiplier
                    size_multiplier *= fgi_mult
                    logger.info(
                        "FGI gate bypassed for %s %s: confluence=%d >= %d, "
                        "size_multiplier reduced by %s",
                        symbol,
                        side,
                        analyst_confluence_score,
                        fgi_bypass,
                        fgi_mult,
                        extra={"symbol": symbol, "side": side},
                    )
                else:
                    logger.info(
                        "Filter chain REJECTED for %s %s by FGI gate: %s",
                        symbol,
                        side,
                        fgi_result.reason,
                        extra={"symbol": symbol, "side": side},
                    )
                    return FilterChainResultSchema(
                        is_allowed=False,
                        rejection_reason=fgi_result.reason,
                        size_multiplier=size_multiplier,
                        results=results,
                        confluence=None,
                        volatility_regime=None,
                        volatility_zscore=None,
                    )

        current_atr = indicators.atr_14 or Decimal(0)
        if current_atr == Decimal(0):
            logger.warning(
                "ATR is zero for %s, volatility detection unreliable",
                symbol,
            )
        if not atr_history:
            logger.warning(
                "ATR history empty for %s, regime defaults to NORMAL",
                symbol,
            )
        regime = self._volatility_detector.detect_regime(current_atr, atr_history)
        tier_multiplier = get_regime_size_multiplier(regime.regime, symbol_tier)
        volatility_allowed = tier_multiplier > Decimal(0)
        volatility_result = FilterResultSchema(
            name="volatility",
            is_allowed=volatility_allowed,
            reason=regime.regime.value,
        )
        results.append(volatility_result)
        logger.debug(
            "Filter volatility: allowed=%s regime=%s zscore=%s tier=%s",
            volatility_allowed,
            regime.regime.value,
            regime.atr_zscore,
            symbol_tier,
        )
        if not volatility_allowed:
            logger.info(
                "Filter chain REJECTED for %s %s by volatility: %s",
                symbol,
                side,
                regime.regime.value,
                extra={"symbol": symbol, "side": side},
            )
            return FilterChainResultSchema(
                is_allowed=False,
                rejection_reason=volatility_result.reason,
                size_multiplier=size_multiplier,
                results=results,
                confluence=None,
                volatility_regime=regime.regime,
                volatility_zscore=regime.atr_zscore,
            )
        # Apply tier-aware regime multiplier
        size_multiplier *= tier_multiplier

        funding_result = self._funding_filter.evaluate(
            side=side,
            order_flow=order_flow,
            symbol=symbol,
        )
        results.append(funding_result)
        logger.debug(
            "Filter funding: allowed=%s reason=%s",
            funding_result.is_allowed,
            funding_result.reason,
        )
        if not funding_result.is_allowed:
            logger.info(
                "Filter chain REJECTED for %s %s by funding: %s",
                symbol,
                side,
                funding_result.reason,
                extra={"symbol": symbol, "side": side},
            )
            return FilterChainResultSchema(
                is_allowed=False,
                rejection_reason=funding_result.reason,
                size_multiplier=size_multiplier,
                results=results,
                confluence=None,
                volatility_regime=regime.regime,
                volatility_zscore=regime.atr_zscore,
            )

        movement_result = self._movement_filter.evaluate(
            candle=candle,
            atr=indicators.atr_14,
        )
        results.append(movement_result)
        logger.debug(
            "Filter movement: allowed=%s reason=%s",
            movement_result.is_allowed,
            movement_result.reason,
        )
        if not movement_result.is_allowed:
            bypass_threshold = self._config.movement_bypass_confluence_min
            if (
                analyst_confluence_score is not None
                and analyst_confluence_score >= bypass_threshold
            ):
                logger.info(
                    "Movement filter bypassed for %s %s: confluence=%d >= %d",
                    symbol,
                    side,
                    analyst_confluence_score,
                    bypass_threshold,
                    extra={"symbol": symbol, "side": side},
                )
            else:
                logger.info(
                    "Filter chain REJECTED for %s %s by movement: %s",
                    symbol,
                    side,
                    movement_result.reason,
                    extra={"symbol": symbol, "side": side},
                )
                return FilterChainResultSchema(
                    is_allowed=False,
                    rejection_reason=movement_result.reason,
                    size_multiplier=size_multiplier,
                    results=results,
                    confluence=None,
                    volatility_regime=regime.regime,
                    volatility_zscore=regime.atr_zscore,
                )

        # --- Spike cooldown (reject impulse candles) ---
        if self._spike_cooldown_filter is not None:
            spike_result = self._spike_cooldown_filter.evaluate(
                candle=candle,
                atr=indicators.atr_14,
            )
            results.append(spike_result)
            logger.debug(
                "Filter spike_cooldown: allowed=%s reason=%s",
                spike_result.is_allowed,
                spike_result.reason,
            )
            if not spike_result.is_allowed:
                logger.info(
                    "Filter chain REJECTED for %s %s by spike cooldown: %s",
                    symbol,
                    side,
                    spike_result.reason,
                    extra={"symbol": symbol, "side": side},
                )
                return FilterChainResultSchema(
                    is_allowed=False,
                    rejection_reason=spike_result.reason,
                    size_multiplier=size_multiplier,
                    results=results,
                    confluence=None,
                    volatility_regime=regime.regime,
                    volatility_zscore=regime.atr_zscore,
                )

        exposure_check = self._exposure_limiter.check_exposure(symbol, positions)
        exposure_result = FilterResultSchema(
            name="position",
            is_allowed=exposure_check.is_allowed,
            reason=exposure_check.rejection_reason,
        )
        results.append(exposure_result)
        logger.debug(
            "Filter exposure: allowed=%s positions=%d/%d",
            exposure_check.is_allowed,
            exposure_check.current_position_count,
            exposure_check.max_positions,
        )
        if not exposure_result.is_allowed:
            logger.info(
                "Filter chain REJECTED for %s %s by exposure: %s",
                symbol,
                side,
                exposure_result.reason,
                extra={"symbol": symbol, "side": side},
            )
            return FilterChainResultSchema(
                is_allowed=False,
                rejection_reason=exposure_result.reason,
                size_multiplier=size_multiplier,
                results=results,
                confluence=None,
                volatility_regime=regime.regime,
                volatility_zscore=regime.atr_zscore,
            )

        liquidity_result = self._liquidity_filter.evaluate()
        size_multiplier *= liquidity_result.size_multiplier
        results.append(liquidity_result)
        logger.debug(
            "Filter liquidity: period=%s multiplier=%s",
            liquidity_result.period,
            liquidity_result.size_multiplier,
        )

        correlation_result = self._correlation_filter.evaluate(
            symbol=symbol,
            positions=positions,
        )
        size_multiplier *= correlation_result.size_multiplier
        results.append(correlation_result)
        logger.debug(
            "Filter correlation: reason=%s multiplier=%s",
            correlation_result.reason,
            correlation_result.size_multiplier,
        )

        confluence = self._confluence_calculator.evaluate(
            side=side,
            candle=candle,
            indicators=indicators,
            order_flow=order_flow,
        )

        logger.info(
            "Filter chain PASSED for %s %s, size_mult=%s confluence=%d",
            symbol,
            side,
            size_multiplier,
            confluence.score,
            extra={"symbol": symbol, "side": side},
        )
        return FilterChainResultSchema(
            is_allowed=True,
            rejection_reason=None,
            size_multiplier=size_multiplier,
            results=results,
            confluence=confluence,
            volatility_regime=regime.regime,
            volatility_zscore=regime.atr_zscore,
        )
