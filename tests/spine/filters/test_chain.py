from decimal import Decimal

import pytest

from kavzi_trader.spine.filters.chain import PreTradeFilterChain
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.correlation import CorrelationFilter
from kavzi_trader.spine.filters.funding import FundingRateFilter
from kavzi_trader.spine.filters.liquidity import LiquidityFilter
from kavzi_trader.spine.filters.movement import MinimumMovementFilter
from kavzi_trader.spine.filters.news import NewsEventFilter
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector


@pytest.mark.asyncio
async def test_chain_allows_and_returns_confluence(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    chain = PreTradeFilterChain(
        volatility_detector=VolatilityRegimeDetector(),
        news_filter=NewsEventFilter(filter_config),
        funding_filter=FundingRateFilter(filter_config),
        movement_filter=MinimumMovementFilter(filter_config),
        exposure_limiter=ExposureLimiter(),
        liquidity_filter=LiquidityFilter(filter_config),
        correlation_filter=CorrelationFilter(filter_config),
        confluence_calculator=ConfluenceCalculator(),
    )

    result = await chain.evaluate(
        symbol="BTCUSDT",
        side="LONG",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=sample_order_flow,
        positions=[],
        atr_history=[Decimal(5)] * 10,
        scheduled_events=None,
    )

    assert result.is_allowed is True, "Expected chain to allow trade"
    assert result.confluence is not None, "Expected confluence result"
    assert result.confluence.score == 3, "Expected confluence score from fixtures"


@pytest.mark.asyncio
async def test_chain_blocks_on_funding(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    chain = PreTradeFilterChain(
        volatility_detector=VolatilityRegimeDetector(),
        news_filter=NewsEventFilter(filter_config),
        funding_filter=FundingRateFilter(filter_config),
        movement_filter=MinimumMovementFilter(filter_config),
        exposure_limiter=ExposureLimiter(),
        liquidity_filter=LiquidityFilter(filter_config),
        correlation_filter=CorrelationFilter(filter_config),
        confluence_calculator=ConfluenceCalculator(),
    )
    crowded = sample_order_flow.model_copy(
        update={"funding_zscore": Decimal("3.0")},
    )

    result = await chain.evaluate(
        symbol="BTCUSDT",
        side="LONG",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=crowded,
        positions=[],
        atr_history=[Decimal(5)] * 10,
        scheduled_events=None,
    )

    assert result.is_allowed is False, "Expected chain to block on funding"
    assert result.rejection_reason == "crowded_long", "Expected funding rejection"
