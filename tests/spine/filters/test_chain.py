from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.schemas import (
    ExternalDataSnapshotSchema,
    FearGreedDataSchema,
)
from kavzi_trader.spine.filters.chain import PreTradeFilterChain
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.correlation import CorrelationFilter
from kavzi_trader.spine.filters.fear_greed_gate import FearGreedGateFilter
from kavzi_trader.spine.filters.funding import FundingRateFilter
from kavzi_trader.spine.filters.liquidity import LiquidityFilter
from kavzi_trader.spine.filters.movement import MinimumMovementFilter
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
    )

    assert result.is_allowed is False, "Expected chain to block on funding"
    assert result.rejection_reason == "crowded_long", "Expected funding rejection"


def _small_body_candle() -> CandlestickSchema:
    """Candle with body=0.1, which is below 0.3 * ATR(5) = 1.5."""
    now = datetime.now(UTC)
    return CandlestickSchema(
        open_time=now - timedelta(minutes=5),
        open_price=Decimal(100),
        high_price=Decimal(105),
        low_price=Decimal(95),
        close_price=Decimal("100.1"),
        volume=Decimal(1000),
        close_time=now,
        quote_volume=Decimal(100000),
        trades_count=100,
        taker_buy_base_volume=Decimal(500),
        taker_buy_quote_volume=Decimal(50000),
        interval="5m",
        symbol="NEARUSDT",
    )


@pytest.mark.asyncio
async def test_chain_bypasses_movement_on_high_confluence(
    filter_config,
    sample_indicators,
    sample_order_flow,
) -> None:
    chain = PreTradeFilterChain(
        volatility_detector=VolatilityRegimeDetector(),
        funding_filter=FundingRateFilter(filter_config),
        movement_filter=MinimumMovementFilter(filter_config),
        exposure_limiter=ExposureLimiter(),
        liquidity_filter=LiquidityFilter(filter_config),
        correlation_filter=CorrelationFilter(filter_config),
        confluence_calculator=ConfluenceCalculator(),
        config=filter_config,
    )

    result = await chain.evaluate(
        symbol="NEARUSDT",
        side="LONG",
        candle=_small_body_candle(),
        indicators=sample_indicators,
        order_flow=sample_order_flow,
        positions=[],
        atr_history=[Decimal(5)] * 10,
        analyst_confluence_score=9,
    )

    assert result.is_allowed is True


@pytest.mark.asyncio
async def test_chain_still_blocks_movement_on_low_confluence(
    filter_config,
    sample_indicators,
    sample_order_flow,
) -> None:
    chain = PreTradeFilterChain(
        volatility_detector=VolatilityRegimeDetector(),
        funding_filter=FundingRateFilter(filter_config),
        movement_filter=MinimumMovementFilter(filter_config),
        exposure_limiter=ExposureLimiter(),
        liquidity_filter=LiquidityFilter(filter_config),
        correlation_filter=CorrelationFilter(filter_config),
        confluence_calculator=ConfluenceCalculator(),
        config=filter_config,
    )

    result = await chain.evaluate(
        symbol="NEARUSDT",
        side="LONG",
        candle=_small_body_candle(),
        indicators=sample_indicators,
        order_flow=sample_order_flow,
        positions=[],
        atr_history=[Decimal(5)] * 10,
        analyst_confluence_score=5,
    )

    assert result.is_allowed is False
    assert result.rejection_reason == "small_body"


@pytest.mark.asyncio
async def test_chain_blocks_movement_when_no_confluence_provided(
    filter_config,
    sample_indicators,
    sample_order_flow,
) -> None:
    chain = PreTradeFilterChain(
        volatility_detector=VolatilityRegimeDetector(),
        funding_filter=FundingRateFilter(filter_config),
        movement_filter=MinimumMovementFilter(filter_config),
        exposure_limiter=ExposureLimiter(),
        liquidity_filter=LiquidityFilter(filter_config),
        correlation_filter=CorrelationFilter(filter_config),
        confluence_calculator=ConfluenceCalculator(),
        config=filter_config,
    )

    result = await chain.evaluate(
        symbol="NEARUSDT",
        side="LONG",
        candle=_small_body_candle(),
        indicators=sample_indicators,
        order_flow=sample_order_flow,
        positions=[],
        atr_history=[Decimal(5)] * 10,
    )

    assert result.is_allowed is False
    assert result.rejection_reason == "small_body"


# ---------------------------------------------------------------------------
# FGI gate confluence bypass
# ---------------------------------------------------------------------------


def _make_fgi_cache(value: int) -> ExternalDataCache:
    cache = ExternalDataCache()
    snapshot = ExternalDataSnapshotSchema.model_validate(
        {
            "fear_greed": FearGreedDataSchema.model_validate(
                {
                    "value": value,
                    "classification": "test",
                    "fetched_at": datetime.now(UTC),
                },
            ),
        },
    )
    cache.set_snapshot(snapshot)
    return cache


def _make_chain_with_fgi(
    filter_config: FilterConfigSchema,
    fgi_value: int,
) -> PreTradeFilterChain:
    cache = _make_fgi_cache(fgi_value)
    return PreTradeFilterChain(
        volatility_detector=VolatilityRegimeDetector(),
        funding_filter=FundingRateFilter(filter_config),
        movement_filter=MinimumMovementFilter(filter_config),
        exposure_limiter=ExposureLimiter(),
        liquidity_filter=LiquidityFilter(filter_config),
        correlation_filter=CorrelationFilter(filter_config),
        confluence_calculator=ConfluenceCalculator(),
        fear_greed_gate=FearGreedGateFilter(cache, filter_config),
        config=filter_config,
    )


@pytest.mark.asyncio
async def test_fgi_bypass_high_confluence_allows(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    """FGI=8 should be bypassed when analyst confluence >= 9."""
    chain = _make_chain_with_fgi(filter_config, fgi_value=8)

    result = await chain.evaluate(
        symbol="BTCUSDT",
        side="LONG",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=sample_order_flow,
        positions=[],
        atr_history=[Decimal(5)] * 10,
        analyst_confluence_score=10,
    )

    assert result.is_allowed is True
    assert result.size_multiplier <= Decimal("0.5")


@pytest.mark.asyncio
async def test_fgi_still_blocks_low_confluence(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    """FGI=8 should still block when analyst confluence < 9."""
    chain = _make_chain_with_fgi(filter_config, fgi_value=8)

    result = await chain.evaluate(
        symbol="BTCUSDT",
        side="LONG",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=sample_order_flow,
        positions=[],
        atr_history=[Decimal(5)] * 10,
        analyst_confluence_score=7,
    )

    assert result.is_allowed is False
    assert "Extreme fear" in (result.rejection_reason or "")


@pytest.mark.asyncio
async def test_fgi_no_confluence_still_blocks(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    """FGI=8 should block when no analyst confluence is provided."""
    chain = _make_chain_with_fgi(filter_config, fgi_value=8)

    result = await chain.evaluate(
        symbol="BTCUSDT",
        side="LONG",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=sample_order_flow,
        positions=[],
        atr_history=[Decimal(5)] * 10,
    )

    assert result.is_allowed is False
