"""Futures stream wiring, message routing and dead-feed detection."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from binance.exceptions import ReadLoopClosed

from kavzi_trader.api.binance.websocket.client import BinanceWebsocketClient
from kavzi_trader.api.binance.websocket.stream_manager import StreamManager
from kavzi_trader.orchestrator.providers import live_stream_manager
from kavzi_trader.orchestrator.providers.live_stream_manager import LiveStreamManager

TEST_TIMEOUT_S = 2

_KLINE_PAYLOAD: dict[str, Any] = {
    "e": "kline",
    "E": 1,
    "s": "BTCUSDT",
    "k": {"s": "BTCUSDT", "i": "15m", "x": True},
}


class _FakeSocket:
    """Stands in for ReconnectingWebsocket; replays queued messages then dies."""

    def __init__(self, messages: list[dict[str, Any]], *, die: bool = True) -> None:
        self._messages = list(messages)
        self._die = die

    async def __aenter__(self) -> "_FakeSocket":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def recv(self) -> dict[str, Any]:
        if self._messages:
            return self._messages.pop(0)
        if self._die:
            raise ReadLoopClosed("read loop closed")
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _stream_manager_with_bsm() -> StreamManager:
    manager = StreamManager()
    manager._is_running = True
    manager._bsm = MagicMock()
    return manager


class TestFuturesSockets:
    async def test_kline_handler_uses_futures_socket(self) -> None:
        manager = _stream_manager_with_bsm()
        manager.start = AsyncMock()  # type: ignore[method-assign]
        manager.register_stream = MagicMock()  # type: ignore[method-assign]
        client = BinanceWebsocketClient()
        client.kline_handler.stream_manager = manager

        name = await client.subscribe_kline_stream("BTCUSDT", "15m", AsyncMock())

        assert name == "btcusdt@kline_15m"
        manager.bsm.futures_multiplex_socket.assert_called_once_with(
            streams=["btcusdt@kline_15m"],
        )
        manager.bsm.kline_socket.assert_not_called()

    async def test_ticker_handler_uses_futures_socket(self) -> None:
        manager = _stream_manager_with_bsm()
        manager.start = AsyncMock()  # type: ignore[method-assign]
        manager.register_stream = MagicMock()  # type: ignore[method-assign]
        client = BinanceWebsocketClient()
        client.ticker_handler.stream_manager = manager

        name = await client.subscribe_ticker_stream("BTCUSDT", AsyncMock())

        assert name == "btcusdt@ticker"
        manager.bsm.individual_symbol_ticker_futures_socket.assert_called_once_with(
            symbol="BTCUSDT",
        )
        manager.bsm.symbol_ticker_socket.assert_not_called()


class TestMessageRouting:
    async def test_combined_stream_envelope_is_unwrapped_for_callback(self) -> None:
        manager = StreamManager()
        callback = AsyncMock()
        manager.stream_callbacks["btcusdt@kline_15m"] = callback

        await manager._process_message(
            {"stream": "btcusdt@kline_15m", "data": _KLINE_PAYLOAD},
        )

        callback.assert_awaited_once_with(_KLINE_PAYLOAD)


class TestDeadFeedDetection:
    async def test_recv_loop_death_marks_manager_disconnected(self) -> None:
        manager = _stream_manager_with_bsm()
        manager.register_stream("btcusdt@ticker", _FakeSocket([]), AsyncMock())  # type: ignore[arg-type]

        async with asyncio.timeout(TEST_TIMEOUT_S):
            while manager.is_connected():
                await asyncio.sleep(0.01)

        assert manager.is_connected() is False

    async def test_fatal_error_message_marks_manager_disconnected(self) -> None:
        manager = _stream_manager_with_bsm()
        on_error = MagicMock()
        manager.on_error_callback = on_error

        await manager._process_message(
            {"e": "error", "type": "BinanceWebsocketUnableToConnect", "m": ""},
        )

        assert manager.is_connected() is False
        on_error.assert_called_once()

    async def test_transient_error_message_keeps_manager_connected(self) -> None:
        manager = _stream_manager_with_bsm()

        await manager._process_message(
            {"e": "error", "type": "ConnectionClosedError", "m": "dropped"},
        )

        assert manager.is_connected() is True

    async def test_error_message_is_not_routed_to_stream_callbacks(self) -> None:
        manager = _stream_manager_with_bsm()
        on_message = MagicMock()
        manager.on_message_callback = on_message

        await manager._process_message(
            {"e": "error", "type": "BinanceWebsocketUnableToConnect", "m": ""},
        )

        on_message.assert_not_called()

    async def test_live_stream_manager_returns_when_feed_dies(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(live_stream_manager, "CONNECTION_CHECK_INTERVAL_S", 0.01)
        ws_client = BinanceWebsocketClient()
        manager = ws_client.stream_manager
        manager._is_running = True
        manager.start = AsyncMock()  # type: ignore[method-assign]
        manager.stop = AsyncMock()  # type: ignore[method-assign]
        manager._bsm = MagicMock()
        manager._bsm.futures_multiplex_socket.return_value = _FakeSocket([])
        manager._bsm.individual_symbol_ticker_futures_socket.return_value = (
            _FakeSocket([])
        )
        live = LiveStreamManager(
            ws_client=ws_client,
            cache=MagicMock(),
            symbols=["BTCUSDT"],
            interval="15m",
        )

        async with asyncio.timeout(TEST_TIMEOUT_S):
            await live.start()

        manager.stop.assert_awaited_once()
