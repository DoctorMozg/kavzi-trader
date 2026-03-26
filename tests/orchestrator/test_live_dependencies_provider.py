from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.orchestrator.providers.live_dependencies_provider import (
    ANALYSIS_CANDLES_COUNT,
    SCOUT_CANDLES_COUNT,
    LiveDependenciesProvider,
)
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime, VolatilityRegimeSchema


def _build_candle(minute: int) -> CandlestickSchema:
    close_time = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)
    return CandlestickSchema(
        open_time=close_time - timedelta(minutes=1),
        open_price=Decimal(100),
        high_price=Decimal(101),
        low_price=Decimal(99),
        close_price=Decimal(100),
        volume=Decimal(1),
        close_time=close_time,
        quote_volume=Decimal(1),
        trades_count=1,
        taker_buy_base_volume=Decimal("0.5"),
        taker_buy_quote_volume=Decimal("0.5"),
        interval="1m",
        symbol="BTCUSDT",
    )


def _make_provider() -> LiveDependenciesProvider:
    detector = Mock()
    detector.detect_regime.return_value = VolatilityRegimeSchema(
        regime=VolatilityRegime.NORMAL,
        atr_zscore=Decimal(0),
        size_multiplier=Decimal(1),
        is_tradeable=True,
    )
    cache = Mock()
    candles = [_build_candle(minute) for minute in range(60)]
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(100),
        ema_50=Decimal(99),
        ema_200=Decimal(98),
        sma_20=Decimal(100),
        rsi_14=Decimal(50),
        macd=None,
        bollinger=None,
        atr_14=Decimal(1),
        volume=None,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    cache.get_candles.return_value = candles
    cache.get_indicators.return_value = indicators
    cache.get_current_price.return_value = Decimal(100)
    cache.get_atr_history.return_value = [Decimal(1), Decimal("1.1")]
    cache.get_order_flow.return_value = None
    confluence_calc = Mock()
    confluence_calc.evaluate.return_value = AlgorithmConfluenceSchema(
        ema_alignment=False,
        rsi_favorable=False,
        volume_above_average=False,
        price_at_bollinger=False,
        funding_favorable=False,
        oi_supports_direction=False,
        score=3,
    )
    return LiveDependenciesProvider(
        cache=cache,
        confluence_calculator=confluence_calc,
        volatility_detector=detector,
        state_manager=AsyncMock(),
        exchange=Mock(),
        event_store=Mock(),
        timeframe="1m",
    )


@pytest.mark.asyncio
async def test_scout_returns_full_candle_window() -> None:
    provider = _make_provider()
    deps = await provider.get_scout("BTCUSDT")
    assert len(deps.recent_candles) == SCOUT_CANDLES_COUNT


@pytest.mark.asyncio
async def test_analyst_returns_reduced_candle_window() -> None:
    provider = _make_provider()
    deps = await provider.get_analyst("BTCUSDT")
    assert len(deps.recent_candles) == ANALYSIS_CANDLES_COUNT


@pytest.mark.asyncio
async def test_cycle_cache_is_cleared() -> None:
    provider = _make_provider()
    regime_1 = provider._get_regime("BTCUSDT")
    regime_2 = provider._get_regime("BTCUSDT")
    assert regime_1 == regime_2
    provider.clear_cycle_cache()
    assert len(provider._cycle_cache) == 0
