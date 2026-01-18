from decimal import Decimal
from typing import Literal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.correlation import CorrelationFilter
from kavzi_trader.spine.filters.filter_chain_result_schema import (
    FilterChainResultSchema,
)
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema
from kavzi_trader.spine.filters.funding import FundingRateFilter
from kavzi_trader.spine.filters.liquidity import LiquidityFilter
from kavzi_trader.spine.filters.movement import MinimumMovementFilter
from kavzi_trader.spine.filters.news import NewsEventFilter
from kavzi_trader.spine.filters.news_event_schema import NewsEventSchema
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.schemas import PositionSchema


class PreTradeFilterChain:
    """Runs ordered pre-trade checks and returns a unified decision."""

    def __init__(
        self,
        volatility_detector: VolatilityRegimeDetector,
        news_filter: NewsEventFilter,
        funding_filter: FundingRateFilter,
        movement_filter: MinimumMovementFilter,
        exposure_limiter: ExposureLimiter,
        liquidity_filter: LiquidityFilter,
        correlation_filter: CorrelationFilter,
        confluence_calculator: ConfluenceCalculator,
    ) -> None:
        self._volatility_detector = volatility_detector
        self._news_filter = news_filter
        self._funding_filter = funding_filter
        self._movement_filter = movement_filter
        self._exposure_limiter = exposure_limiter
        self._liquidity_filter = liquidity_filter
        self._correlation_filter = correlation_filter
        self._confluence_calculator = confluence_calculator

    async def evaluate(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        candle: CandlestickSchema,
        indicators: TechnicalIndicatorsSchema,
        order_flow: OrderFlowSchema | None,
        positions: list[PositionSchema],
        atr_history: list[Decimal],
        scheduled_events: list[NewsEventSchema] | None = None,
    ) -> FilterChainResultSchema:
        results: list[FilterResultSchema] = []
        size_multiplier = Decimal("1.0")

        current_atr = indicators.atr_14 or Decimal("0")
        regime = self._volatility_detector.detect_regime(current_atr, atr_history)
        volatility_allowed = regime.regime in {
            VolatilityRegime.NORMAL,
            VolatilityRegime.HIGH,
        }
        volatility_result = FilterResultSchema(
            name="volatility",
            is_allowed=volatility_allowed,
            reason=regime.regime.value,
        )
        results.append(volatility_result)
        if not volatility_allowed:
            return FilterChainResultSchema(
                is_allowed=False,
                rejection_reason=volatility_result.reason,
                size_multiplier=size_multiplier,
                results=results,
                confluence=None,
                volatility_regime=regime.regime,
                volatility_zscore=regime.atr_zscore,
            )

        news_result = self._news_filter.evaluate(
            events=scheduled_events,
        )
        results.append(news_result)
        if not news_result.is_allowed:
            return FilterChainResultSchema(
                is_allowed=False,
                rejection_reason=news_result.reason,
                size_multiplier=size_multiplier,
                results=results,
                confluence=None,
                volatility_regime=regime.regime,
                volatility_zscore=regime.atr_zscore,
            )

        funding_result = self._funding_filter.evaluate(
            side=side,
            order_flow=order_flow,
        )
        results.append(funding_result)
        if not funding_result.is_allowed:
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
        if not movement_result.is_allowed:
            return FilterChainResultSchema(
                is_allowed=False,
                rejection_reason=movement_result.reason,
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
        if not exposure_result.is_allowed:
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

        correlation_result = self._correlation_filter.evaluate(
            symbol=symbol,
            positions=positions,
        )
        size_multiplier *= correlation_result.size_multiplier
        results.append(correlation_result)

        confluence = self._confluence_calculator.evaluate(
            side=side,
            candle=candle,
            indicators=indicators,
            order_flow=order_flow,
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
