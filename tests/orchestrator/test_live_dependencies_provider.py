import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.orchestrator.providers.live_dependencies_provider import (
    LiveDependenciesProvider,
    RECENT_CANDLES_COUNT,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime, VolatilityRegimeSchema


def _build_candle(minute: int) -> CandlestickSchema:
    close_time = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)
    return CandlestickSchema(
        open_time=close_time - timedelta(minutes=1),
        open_price=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100"),
        volume=Decimal("1"),
        close_time=close_time,
        quote_volume=Decimal("1"),
        trades_count=1,
        taker_buy_base_volume=Decimal("0.5"),
        taker_buy_quote_volume=Decimal("0.5"),
        interval="1m",
        symbol="BTCUSDT",
    )


@pytest.mark.asyncio()
async def test_get_scout_logs_cache_and_recent_candle_counts(caplog) -> None:
    candles = [_build_candle(minute) for minute in range(60)]
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal("100"),
        ema_50=Decimal("99"),
        ema_200=Decimal("98"),
        sma_20=Decimal("100"),
        rsi_14=Decimal("50"),
        macd=None,
        bollinger=None,
        atr_14=Decimal("1"),
        volume=None,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    detector = Mock()
    detector.detect_regime.return_value = VolatilityRegimeSchema(
        regime=VolatilityRegime.NORMAL,
        atr_zscore=Decimal("0"),
        size_multiplier=Decimal("1"),
        is_tradeable=True,
    )
    cache = Mock()
    cache.get_candles.return_value = candles
    cache.get_indicators.return_value = indicators
    cache.get_current_price.return_value = Decimal("100")
    cache.get_atr_history.return_value = [Decimal("1"), Decimal("1.1")]

    provider = LiveDependenciesProvider(
        cache=cache,
        confluence_calculator=Mock(),
        volatility_detector=detector,
        state_manager=AsyncMock(),
        exchange=Mock(),
        event_store=Mock(),
        timeframe="1m",
    )

    with caplog.at_level(logging.DEBUG):
        deps = await provider.get_scout("BTCUSDT")

    assert len(deps.recent_candles) == RECENT_CANDLES_COUNT
    assert (
        "Scout dependencies for BTCUSDT: cache_candles=60 recent_candles=50 "
        "timeframe=1m" in caplog.text
    )
