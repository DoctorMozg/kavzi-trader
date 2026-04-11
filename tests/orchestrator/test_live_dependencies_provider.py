import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.config import FuturesConfigSchema
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.schemas import SentimentSummarySchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.orchestrator.providers.live_dependencies_provider import (
    ANALYSIS_CANDLES_COUNT,
    SCOUT_CANDLES_COUNT,
    LiveDependenciesProvider,
)
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
    DualConfluenceSchema,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime, VolatilityRegimeSchema
from kavzi_trader.spine.state.schemas import AccountStateSchema


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


def _make_provider(
    futures_config: FuturesConfigSchema | None = None,
    external_cache: ExternalDataCache | None = None,
) -> LiveDependenciesProvider:
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
    cache.get_atr_pct_history.return_value = [Decimal("1.0"), Decimal("1.1")]
    cache.get_order_flow.return_value = None
    confluence_calc = Mock()
    single_conf = AlgorithmConfluenceSchema(
        ema_alignment=False,
        rsi_favorable=False,
        volume_above_average=False,
        price_at_bollinger=False,
        funding_favorable=False,
        oi_supports_direction=False,
        oi_funding_divergence=False,
        volume_spike=False,
        score=0,
    )
    confluence_calc.evaluate_both.return_value = DualConfluenceSchema(
        long=single_conf,
        short=single_conf,
        detected_side="LONG",
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state_manager = AsyncMock()
    state_manager.get_account_state = AsyncMock(
        return_value=AccountStateSchema(
            total_balance_usdt=Decimal(10000),
            available_balance_usdt=Decimal(8000),
            locked_balance_usdt=Decimal(2000),
            unrealized_pnl=Decimal(0),
            peak_balance=Decimal(10000),
            current_drawdown_percent=Decimal(0),
            updated_at=now,
        ),
    )
    state_manager.get_all_positions = AsyncMock(return_value=[])
    return LiveDependenciesProvider(
        cache=cache,
        confluence_calculator=confluence_calc,
        volatility_detector=detector,
        state_manager=state_manager,
        exchange=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
        timeframe="1m",
        futures_config=futures_config,
        external_cache=external_cache,
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


@pytest.mark.asyncio
async def test_trader_deps_include_default_leverage() -> None:
    provider = _make_provider()
    deps = await provider.get_trader("BTCUSDT")
    assert deps.leverage == 5


@pytest.mark.asyncio
async def test_analyst_deps_include_default_leverage() -> None:
    provider = _make_provider()
    deps = await provider.get_analyst("BTCUSDT")
    assert deps.leverage == 5


@pytest.mark.asyncio
async def test_symbol_specific_leverage() -> None:
    provider = _make_provider(
        futures_config=FuturesConfigSchema.model_validate(
            {"symbol_leverage": {"BTCUSDT": 5}},
        ),
    )
    deps = await provider.get_trader("BTCUSDT")
    assert deps.leverage == 5


@pytest.mark.asyncio
async def test_analyst_deps_include_sentiment_when_cache_set() -> None:
    ext_cache = ExternalDataCache()
    summary = SentimentSummarySchema(
        summary="Fear in the market.",
        sentiment_bias="BEARISH",
        confidence_adjustment=Decimal("-0.05"),
    )
    ext_cache.set_sentiment_summary(summary)
    provider = _make_provider(external_cache=ext_cache)
    deps = await provider.get_analyst("BTCUSDT")
    assert deps.sentiment_summary is not None
    assert deps.sentiment_summary.sentiment_bias == "BEARISH"


@pytest.mark.asyncio
async def test_trader_deps_include_sentiment_when_cache_set() -> None:
    ext_cache = ExternalDataCache()
    summary = SentimentSummarySchema(
        summary="Market is neutral.",
        sentiment_bias="NEUTRAL",
        confidence_adjustment=Decimal("0.00"),
    )
    ext_cache.set_sentiment_summary(summary)
    provider = _make_provider(external_cache=ext_cache)
    deps = await provider.get_trader("BTCUSDT")
    assert deps.sentiment_summary is not None
    assert deps.sentiment_summary.sentiment_bias == "NEUTRAL"


@pytest.mark.asyncio
async def test_deps_sentiment_none_without_cache() -> None:
    provider = _make_provider()
    deps = await provider.get_analyst("BTCUSDT")
    assert deps.sentiment_summary is None


@pytest.mark.asyncio
async def test_confluence_computed_once_per_cycle() -> None:
    """Confluence should be cached after first call within a cycle."""
    provider = _make_provider()
    await provider.get_analyst("BTCUSDT")
    await provider.get_trader("BTCUSDT")
    provider._confluence.evaluate_both.assert_called_once()


class _FrozenDatetime(datetime):
    """datetime subclass that lets tests pin `datetime.now(UTC)`."""

    _frozen: datetime

    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return cls._frozen


def _freeze_provider_now(
    monkeypatch: pytest.MonkeyPatch,
    frozen: datetime,
) -> None:
    from kavzi_trader.orchestrator.providers import live_dependencies_provider

    _FrozenDatetime._frozen = frozen
    monkeypatch.setattr(live_dependencies_provider, "datetime", _FrozenDatetime)


def test_get_sentiment_warns_when_stale(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ext_cache = ExternalDataCache()
    summary = SentimentSummarySchema(
        summary="Stale summary.",
        sentiment_bias="NEUTRAL",
        confidence_adjustment=Decimal("0.00"),
    )
    ext_cache.set_sentiment_summary(summary)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(
        ext_cache,
        "get_sentiment_updated_at",
        lambda: now - timedelta(seconds=2000),
    )
    _freeze_provider_now(monkeypatch, now)

    provider = _make_provider(external_cache=ext_cache)
    with caplog.at_level(
        logging.WARNING,
        logger="kavzi_trader.orchestrator.providers.live_dependencies_provider",
    ):
        result = provider._get_sentiment()

    assert result is summary
    stale_records = [r for r in caplog.records if "Sentiment stale" in r.message]
    assert len(stale_records) == 1
    assert stale_records[0].levelno == logging.WARNING


def test_get_sentiment_no_warn_when_fresh(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ext_cache = ExternalDataCache()
    summary = SentimentSummarySchema(
        summary="Fresh summary.",
        sentiment_bias="NEUTRAL",
        confidence_adjustment=Decimal("0.00"),
    )
    ext_cache.set_sentiment_summary(summary)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(
        ext_cache,
        "get_sentiment_updated_at",
        lambda: now - timedelta(seconds=900),
    )
    _freeze_provider_now(monkeypatch, now)

    provider = _make_provider(external_cache=ext_cache)
    with caplog.at_level(
        logging.WARNING,
        logger="kavzi_trader.orchestrator.providers.live_dependencies_provider",
    ):
        result = provider._get_sentiment()

    assert result is summary
    assert not any("Sentiment stale" in r.message for r in caplog.records)


def test_get_sentiment_no_warn_at_exact_threshold(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Boundary: age == 1800s should NOT warn (strict `>` comparison)."""
    ext_cache = ExternalDataCache()
    summary = SentimentSummarySchema(
        summary="Boundary summary.",
        sentiment_bias="NEUTRAL",
        confidence_adjustment=Decimal("0.00"),
    )
    ext_cache.set_sentiment_summary(summary)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(
        ext_cache,
        "get_sentiment_updated_at",
        lambda: now - timedelta(seconds=1800),
    )
    _freeze_provider_now(monkeypatch, now)

    provider = _make_provider(external_cache=ext_cache)
    with caplog.at_level(
        logging.WARNING,
        logger="kavzi_trader.orchestrator.providers.live_dependencies_provider",
    ):
        provider._get_sentiment()

    assert not any("Sentiment stale" in r.message for r in caplog.records)
