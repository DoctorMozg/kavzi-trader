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
from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.schemas import VolatilityRegime
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


_WEDNESDAY_NOON = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)
_SATURDAY_NOON = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
_HIGH_ATR_HISTORY = [Decimal(str(i)) for i in [3, 4, 5, 4, 3, 4, 5, 4, 3, 4]]
_EXTREME_ATR_HISTORY = [
    Decimal(str(i)) for i in ["2", "2", "2.1", "1.9", "2", "2", "2.1", "1.9", "2", "2"]
]


def _make_chain(
    filter_config: FilterConfigSchema,
    now: datetime = _WEDNESDAY_NOON,
    risk_config: RiskConfigSchema | None = None,
) -> PreTradeFilterChain:
    return PreTradeFilterChain(
        volatility_detector=VolatilityRegimeDetector(risk_config),
        funding_filter=FundingRateFilter(filter_config),
        movement_filter=MinimumMovementFilter(filter_config),
        exposure_limiter=ExposureLimiter(),
        liquidity_filter=LiquidityFilter(filter_config, time_provider=lambda: now),
        correlation_filter=CorrelationFilter(filter_config),
        confluence_calculator=ConfluenceCalculator(),
        config=filter_config,
    )


@pytest.mark.asyncio
async def test_chain_size_multiplier_combines_weekend_and_funding(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    """Weekend 0.5 x adverse funding (z=1.0) 0.8 = 0.4."""
    chain = _make_chain(filter_config, now=_SATURDAY_NOON)

    result = await chain.evaluate(
        symbol="BTCUSDT",
        side="LONG",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=sample_order_flow,
        positions=[],
        atr_history=[Decimal(5)] * 10,
    )

    assert result.is_allowed is True
    assert result.size_multiplier == Decimal("0.4")


@pytest.mark.asyncio
async def test_chain_size_multiplier_excludes_regime_multiplier(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    """The sizer applies the HIGH 0.5 itself; the chain must not apply it twice."""
    chain = _make_chain(filter_config)
    flat_funding = sample_order_flow.model_copy(
        update={"funding_zscore": Decimal(0)},
    )

    result = await chain.evaluate(
        symbol="BTCUSDT",
        side="LONG",
        candle=sample_candle,
        indicators=sample_indicators,
        order_flow=flat_funding,
        positions=[],
        atr_history=_HIGH_ATR_HISTORY,
    )

    liquidity = LiquidityFilter(filter_config).evaluate(_WEDNESDAY_NOON)
    assert result.is_allowed is True
    assert result.volatility_regime == VolatilityRegime.HIGH
    assert result.size_multiplier == liquidity.size_multiplier


@pytest.mark.asyncio
async def test_chain_extreme_allows_tier1_and_blocks_tier2(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    chain = _make_chain(filter_config)
    common = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "candle": sample_candle,
        "indicators": sample_indicators,
        "order_flow": sample_order_flow,
        "positions": [],
        "atr_history": _EXTREME_ATR_HISTORY,
    }

    tier1 = await chain.evaluate(**common, symbol_tier="TIER_1")
    tier2 = await chain.evaluate(**common, symbol_tier="TIER_2")

    assert tier1.is_allowed is True
    assert tier1.volatility_regime == VolatilityRegime.EXTREME
    assert tier2.is_allowed is False
    assert tier2.rejection_reason == "EXTREME"


@pytest.mark.asyncio
async def test_chain_extreme_confidence_override_matches_validator(
    filter_config,
    sample_candle,
    sample_indicators,
    sample_order_flow,
) -> None:
    chain = _make_chain(
        filter_config,
        risk_config=RiskConfigSchema(extreme_high_confidence_pass=True),
    )
    common = {
        "symbol": "SOLUSDT",
        "side": "LONG",
        "candle": sample_candle,
        "indicators": sample_indicators,
        "order_flow": sample_order_flow,
        "positions": [],
        "atr_history": _EXTREME_ATR_HISTORY,
        "symbol_tier": "TIER_2",
    }

    confident = await chain.evaluate(**common, confidence=Decimal("0.85"))
    unsure = await chain.evaluate(**common, confidence=Decimal("0.70"))

    assert confident.is_allowed is True
    assert unsure.is_allowed is False
