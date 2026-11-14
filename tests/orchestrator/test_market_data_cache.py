from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.orchestrator.providers.market_data_cache import (
    ATR_HISTORY_LENGTH,
    MarketDataCache,
)

SYMBOL = "BTCUSDT"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index: int, close: Decimal | None = None) -> CandlestickSchema:
    base = Decimal(100 + index % 7)
    close_price = close if close is not None else base + Decimal("0.5")
    return CandlestickSchema(
        open_time=T0 + timedelta(minutes=15 * index),
        open_price=base,
        high_price=base + 3,
        low_price=base - 2,
        close_price=close_price,
        volume=Decimal(1000),
        close_time=T0 + timedelta(minutes=15 * index + 14),
        quote_volume=Decimal(100000),
        trades_count=100,
        taker_buy_base_volume=Decimal(500),
        taker_buy_quote_volume=Decimal(50000),
        interval="15m",
        symbol=SYMBOL,
    )


def _exchange_with(candles: list[CandlestickSchema]) -> AsyncMock:
    exchange = AsyncMock()
    exchange.get_klines.return_value = candles
    return exchange


@pytest.fixture
def cache() -> MarketDataCache:
    return MarketDataCache([SYMBOL], TechnicalIndicatorCalculator(), max_candles=100)


class TestInitialize:
    async def test_backfill_sets_candles_price_and_indicators(
        self,
        cache: MarketDataCache,
    ) -> None:
        candles = [_candle(i) for i in range(60)]

        await cache.initialize(_exchange_with(candles), "15m")

        assert cache.get_candles(SYMBOL) == candles
        assert cache.get_current_price(SYMBOL) == candles[-1].close_price
        indicators = cache.get_indicators(SYMBOL)
        assert indicators is not None
        assert indicators.atr_14 is not None
        assert indicators.atr_14 > 0

    async def test_enough_history_seeds_full_atr_windows(
        self,
        cache: MarketDataCache,
    ) -> None:
        await cache.initialize(_exchange_with([_candle(i) for i in range(60)]), "15m")

        atr_history = cache.get_atr_history(SYMBOL)
        atr_pct_history = cache.get_atr_pct_history(SYMBOL)
        assert len(atr_history) == ATR_HISTORY_LENGTH
        assert len(atr_pct_history) == ATR_HISTORY_LENGTH
        # The newest seeded window covers all candles, so it matches the live ATR.
        assert atr_history[-1] == cache.get_atr(SYMBOL)

    async def test_short_history_seeds_a_single_entry(
        self,
        cache: MarketDataCache,
    ) -> None:
        candles = [_candle(i) for i in range(20)]

        await cache.initialize(_exchange_with(candles), "15m")

        assert cache.get_atr_history(SYMBOL) == [cache.get_atr(SYMBOL)]
        expected_pct = cache.get_atr(SYMBOL) / candles[-1].close_price * Decimal(100)
        assert cache.get_atr_pct_history(SYMBOL) == [expected_pct]

    async def test_history_shorter_than_atr_period_seeds_nothing(
        self,
        cache: MarketDataCache,
    ) -> None:
        await cache.initialize(_exchange_with([_candle(i) for i in range(5)]), "15m")

        assert cache.get_atr_history(SYMBOL) == []
        assert cache.get_atr_pct_history(SYMBOL) == []

    async def test_empty_backfill_leaves_cache_empty(
        self,
        cache: MarketDataCache,
    ) -> None:
        await cache.initialize(_exchange_with([]), "15m")

        assert cache.get_candles(SYMBOL) == []
        assert cache.get_indicators(SYMBOL) is None
        assert cache.get_atr(SYMBOL) == Decimal(0)

    async def test_rest_failure_for_one_symbol_does_not_abort_others(self) -> None:
        cache = MarketDataCache(
            ["ETHUSDT", SYMBOL],
            TechnicalIndicatorCalculator(),
            max_candles=100,
        )
        candles = [_candle(i) for i in range(10)]
        exchange = AsyncMock()
        exchange.get_klines.side_effect = [RuntimeError("rest down"), candles]

        await cache.initialize(exchange, "15m")

        assert cache.get_candles("ETHUSDT") == []
        assert cache.get_candles(SYMBOL) == candles


class TestUpdateCandle:
    async def test_new_closed_candle_is_appended_and_indicators_recomputed(
        self,
        cache: MarketDataCache,
    ) -> None:
        await cache.initialize(_exchange_with([_candle(i) for i in range(60)]), "15m")
        before = cache.get_indicators(SYMBOL)
        new_candle = _candle(60, close=Decimal(150))

        await cache.update_candle(SYMBOL, new_candle, is_closed=True)

        assert len(cache.get_candles(SYMBOL)) == 61
        assert cache.get_candles(SYMBOL)[-1] == new_candle
        assert cache.get_current_price(SYMBOL) == Decimal(150)
        after = cache.get_indicators(SYMBOL)
        assert after is not None
        assert after != before
        assert len(cache.get_atr_history(SYMBOL)) == ATR_HISTORY_LENGTH
        assert cache.get_atr_history(SYMBOL)[-1] == after.atr_14

    async def test_closed_candle_with_same_open_time_replaces_last(
        self,
        cache: MarketDataCache,
    ) -> None:
        candles = [_candle(i) for i in range(60)]
        await cache.initialize(_exchange_with(candles), "15m")
        revised = _candle(59, close=Decimal(120))

        await cache.update_candle(SYMBOL, revised, is_closed=True)

        stored = cache.get_candles(SYMBOL)
        assert len(stored) == 60
        assert stored[-1] == revised
        assert stored[:-1] == candles[:-1]

    async def test_atr_pct_is_atr_relative_to_the_closing_price(
        self,
        cache: MarketDataCache,
    ) -> None:
        await cache.initialize(_exchange_with([_candle(i) for i in range(20)]), "15m")
        candle = _candle(20, close=Decimal(200))

        await cache.update_candle(SYMBOL, candle, is_closed=True)

        atr = cache.get_atr(SYMBOL)
        assert atr > 0
        assert cache.get_atr_pct_history(SYMBOL)[-1] == atr / Decimal(200) * 100
        assert len(cache.get_atr_pct_history(SYMBOL)) == 2

    async def test_open_candle_only_moves_price(self, cache: MarketDataCache) -> None:
        await cache.initialize(_exchange_with([_candle(i) for i in range(60)]), "15m")
        candles_before = cache.get_candles(SYMBOL)
        indicators_before = cache.get_indicators(SYMBOL)
        atr_history_before = cache.get_atr_history(SYMBOL)

        await cache.update_candle(
            SYMBOL,
            _candle(40, close=Decimal(130)),
            is_closed=False,
        )

        assert cache.get_current_price(SYMBOL) == Decimal(130)
        assert cache.get_candles(SYMBOL) == candles_before
        assert cache.get_indicators(SYMBOL) == indicators_before
        assert cache.get_atr_history(SYMBOL) == atr_history_before

    async def test_candle_window_is_capped_at_max_candles(self) -> None:
        cache = MarketDataCache([SYMBOL], TechnicalIndicatorCalculator(), max_candles=5)

        for i in range(8):
            await cache.update_candle(SYMBOL, _candle(i), is_closed=True)

        stored = cache.get_candles(SYMBOL)
        assert [c.open_time for c in stored] == [
            _candle(i).open_time for i in range(3, 8)
        ]

    async def test_unknown_symbol_is_ignored(self, cache: MarketDataCache) -> None:
        await cache.update_candle("XRPUSDT", _candle(0), is_closed=True)
        await cache.update_price("XRPUSDT", Decimal(1))

        assert cache.get_candles("XRPUSDT") == []
        assert cache.get_current_price("XRPUSDT") == Decimal(0)
        assert cache.get_atr_history("XRPUSDT") == []
