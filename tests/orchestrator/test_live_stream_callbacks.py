"""Parsing of raw Binance kline/ticker events by LiveStreamManager callbacks."""

from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.api.binance.schemas.data_dicts import KlineData, TickerData
from kavzi_trader.api.binance.websocket.client import BinanceWebsocketClient
from kavzi_trader.api.binance.websocket.stream_manager import StreamManager
from kavzi_trader.orchestrator.providers.live_stream_manager import LiveStreamManager
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache

KLINE_STREAM = "btcusdt@kline_15m"


def _kline_event(*, closed: bool = True, symbol: str = "BTCUSDT") -> dict[str, Any]:
    return {
        "e": "kline",
        "E": 1_700_000_900_000,
        "s": symbol,
        "k": {
            "t": 1_700_000_000_000,
            "T": 1_700_000_899_999,
            "s": symbol,
            "i": "15m",
            "o": "100.5",
            "c": "101.25",
            "h": "102.0",
            "l": "99.75",
            "v": "12.5",
            "n": 42,
            "x": closed,
            "q": "1260.0",
            "V": "6.0",
            "Q": "600.0",
        },
    }


def _ticker_event(price: str = "123.45") -> dict[str, Any]:
    return {"e": "24hrTicker", "E": 1, "s": "BTCUSDT", "c": price}


@pytest.fixture
def cache() -> MagicMock:
    mock = MagicMock(spec=MarketDataCache)
    mock.update_candle = AsyncMock()
    mock.update_price = AsyncMock()
    return mock


@pytest.fixture
def manager(cache: MagicMock) -> LiveStreamManager:
    return LiveStreamManager(
        ws_client=cast("BinanceWebsocketClient", MagicMock()),
        cache=cast("MarketDataCache", cache),
        symbols=["BTCUSDT"],
        interval="15m",
    )


class TestOnKline:
    async def test_closed_kline_becomes_a_candle_in_the_cache(
        self,
        manager: LiveStreamManager,
        cache: MagicMock,
    ) -> None:
        await manager._on_kline(cast("KlineData", _kline_event()))

        cache.update_candle.assert_awaited_once()
        symbol, candle = cache.update_candle.await_args.args
        assert symbol == "BTCUSDT"
        assert cache.update_candle.await_args.kwargs == {"is_closed": True}
        assert candle.open_time.timestamp() == 1_700_000_000
        assert candle.close_time.timestamp() == pytest.approx(1_700_000_899.999)
        assert candle.open_price == Decimal("100.5")
        assert candle.high_price == Decimal("102.0")
        assert candle.low_price == Decimal("99.75")
        assert candle.close_price == Decimal("101.25")
        assert candle.volume == Decimal("12.5")
        assert candle.quote_volume == Decimal("1260.0")
        assert candle.trades_count == 42
        assert candle.taker_buy_base_volume == Decimal("6.0")
        assert candle.taker_buy_quote_volume == Decimal("600.0")
        assert (candle.interval, candle.symbol) == ("15m", "BTCUSDT")

    async def test_open_kline_is_flagged_not_closed(
        self,
        manager: LiveStreamManager,
        cache: MagicMock,
    ) -> None:
        await manager._on_kline(cast("KlineData", _kline_event(closed=False)))

        assert cache.update_candle.await_args.kwargs == {"is_closed": False}

    async def test_malformed_kline_is_logged_and_does_not_raise(
        self,
        manager: LiveStreamManager,
        cache: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        event = _kline_event()
        del event["k"]["c"]

        with caplog.at_level("ERROR"):
            await manager._on_kline(cast("KlineData", event))

        cache.update_candle.assert_not_awaited()
        assert "Error processing kline data" in caplog.text

    async def test_multiplex_envelope_reaches_cache_via_stream_manager(
        self,
        manager: LiveStreamManager,
        cache: MagicMock,
    ) -> None:
        stream_manager = StreamManager()
        stream_manager.add_stream_callback(
            KLINE_STREAM,
            cast("Any", manager._on_kline),
        )

        await stream_manager._process_message(
            {"stream": KLINE_STREAM, "data": _kline_event()},
        )

        cache.update_candle.assert_awaited_once()
        assert cache.update_candle.await_args.args[1].close_price == Decimal("101.25")


class TestOnTicker:
    async def test_last_price_updates_the_cache(
        self,
        manager: LiveStreamManager,
        cache: MagicMock,
    ) -> None:
        await manager._on_ticker(cast("TickerData", _ticker_event("123.45")))

        cache.update_price.assert_awaited_once_with("BTCUSDT", Decimal("123.45"))

    async def test_bad_price_is_logged_and_does_not_raise(
        self,
        manager: LiveStreamManager,
        cache: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level("ERROR"):
            await manager._on_ticker(cast("TickerData", _ticker_event("not-a-number")))

        cache.update_price.assert_not_awaited()
        assert "Error processing ticker data" in caplog.text
