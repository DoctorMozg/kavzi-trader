"""
Tests for Binance WebSocket client.

This module contains tests for the Binance WebSocket client implementation.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from src.api.binance import BinanceWebsocketClient
from src.api.binance.websocket import CallbackType


@pytest_asyncio.fixture
async def ws_client() -> AsyncGenerator[BinanceWebsocketClient, None]:
    """Create a Binance WebSocket client for testing."""
    client = BinanceWebsocketClient(testnet=True)
    yield client
    # Cleanup
    await client.unsubscribe_all_streams()


@pytest.mark.asyncio()
async def test_kline_stream(ws_client: BinanceWebsocketClient) -> None:
    """Test kline stream subscription and message handling."""
    # Mock the callback function
    callback = MagicMock()

    # Cast the mock to the correct type for type checking purposes
    typed_callback = cast(CallbackType, callback)

    # Start the WebSocket client with a mock
    with patch.object(ws_client, "_start_websocket", return_value=None) as mock_start:
        # Subscribe to kline stream
        await ws_client.subscribe_kline_stream("BTCUSDT", "1m", typed_callback)

        # Verify that the WebSocket was started
        mock_start.assert_called_once()

        # Check that the stream was added correctly
        assert len(ws_client.active_streams) == 1
        stream_name = "btcusdt@kline_1m"
        assert stream_name in ws_client.active_streams

        # Manually trigger the callback to simulate a message
        test_data: dict[str, Any] = {
            "e": "kline",
            "E": 1672515782136,
            "s": "BTCUSDT",
            "k": {
                "t": 1672515780000,
                "T": 1672515839999,
                "s": "BTCUSDT",
                "i": "1m",
                "f": 100,
                "L": 200,
                "o": "16500.00",
                "c": "16510.00",
                "h": "16515.00",
                "l": "16498.00",
                "v": "10.5",
                "n": 100,
                "x": False,
                "q": "173250.00",
                "V": "5.2",
                "Q": "86000.00",
                "B": "0",
            },
        }

        # Simulate message processing
        await ws_client._process_message(stream_name, test_data)

        # Check that the callback was called with the processed data
        callback.assert_called_once()

        # Unsubscribe from the stream
        await ws_client.unsubscribe_stream(stream_name)

        # Check that the stream was removed
        assert len(ws_client.active_streams) == 0


@pytest.mark.asyncio()
async def test_ticker_stream(ws_client: BinanceWebsocketClient) -> None:
    """Test ticker stream subscription and message handling."""
    callback = MagicMock()
    typed_callback = cast(CallbackType, callback)

    with patch.object(ws_client, "_start_websocket", return_value=None) as mock_start:
        # Subscribe to ticker stream
        await ws_client.subscribe_ticker_stream("BTCUSDT", typed_callback)

        mock_start.assert_called_once()
        assert len(ws_client.active_streams) == 1
        stream_name = "btcusdt@ticker"
        assert stream_name in ws_client.active_streams

        # Clean up
        await ws_client.unsubscribe_stream(stream_name)
        assert len(ws_client.active_streams) == 0


@pytest.mark.asyncio()
async def test_order_book_stream(ws_client: BinanceWebsocketClient) -> None:
    """Test order book stream subscription and message handling."""
    callback = MagicMock()

    with patch.object(ws_client, "_start_websocket", return_value=None) as mock_start:
        # Subscribe to depth stream
        await ws_client.subscribe_depth_stream(
            "BTCUSDT",
            callback,
            update_speed="100ms",
        )

        mock_start.assert_called_once()
        assert len(ws_client.active_streams) == 1
        stream_name = "btcusdt@depth@100ms"
        assert stream_name in ws_client.active_streams

        # Clean up
        await ws_client.unsubscribe_stream(stream_name)
        assert len(ws_client.active_streams) == 0


@pytest.mark.asyncio()
async def test_trades_stream(ws_client: BinanceWebsocketClient) -> None:
    """Test trades stream subscription and message handling."""
    callback = MagicMock()

    with patch.object(ws_client, "_start_websocket", return_value=None) as mock_start:
        # Subscribe to trades stream
        await ws_client.subscribe_trades_stream("BTCUSDT", callback)

        mock_start.assert_called_once()
        assert len(ws_client.active_streams) == 1
        stream_name = "btcusdt@trade"
        assert stream_name in ws_client.active_streams

        # Manually trigger the callback with test data
        test_data = {
            "e": "trade",
            "E": 1672515782136,
            "s": "BTCUSDT",
            "t": 12345,
            "p": "16500.00",
            "q": "0.5",
            "b": 88,
            "a": 99,
            "T": 1672515782136,
            "m": True,
            "M": True,
        }

        ws_client._process_message(stream_name, test_data)
        callback.assert_called_once()

        # Clean up
        await ws_client.unsubscribe_stream(stream_name)
        assert len(ws_client.active_streams) == 0


@pytest.mark.asyncio()
async def test_multiple_streams(ws_client: BinanceWebsocketClient) -> None:
    """Test subscribing to multiple streams."""
    callback1 = MagicMock()
    callback2 = MagicMock()
    typed_callback1 = cast(CallbackType, callback1)
    typed_callback2 = cast(CallbackType, callback2)

    with patch.object(ws_client, "_start_websocket", return_value=None) as mock_start:
        # Subscribe to multiple streams
        await ws_client.subscribe_kline_stream("BTCUSDT", "1m", typed_callback1)
        await ws_client.subscribe_ticker_stream("ETHUSDT", typed_callback2)

        assert mock_start.call_count == 2
        assert len(ws_client.active_streams) == 2

        # Check that both streams are active
        assert "btcusdt@kline_1m" in ws_client.active_streams
        assert "ethusdt@ticker" in ws_client.active_streams

        # Clean up
        await ws_client.unsubscribe_all_streams()
        assert len(ws_client.active_streams) == 0


@pytest.mark.asyncio()
async def test_error_handling(ws_client: BinanceWebsocketClient) -> None:
    """Test error handling in WebSocket client."""
    # Test with a mock error_callback
    error_callback = MagicMock()

    # Create a client with an error callback
    client_with_error_cb = BinanceWebsocketClient(
        testnet=True,
        error_callback=error_callback,
    )

    # Simulate an error
    error = Exception("Test error")
    client_with_error_cb._on_error(error)

    # Check that the error callback was called with the error
    error_callback.assert_called_once_with(error)


@pytest.mark.asyncio()
async def test_async_callback() -> None:
    """Test using async callbacks with WebSocket client."""

    # Define an async callback function
    async def async_callback(message: dict[str, Any]) -> None:
        pass

    # Create a mock for this async function
    async_mock = MagicMock()
    async_mock.__call__ = MagicMock(return_value=None)

    # Check if is coroutine function
    assert asyncio.iscoroutinefunction(async_callback)

    # Create client with the async callback
    client = BinanceWebsocketClient(testnet=True)

    # Test the _process_message method with an async callback
    with patch.object(
        client,
        "stream_callbacks",
        {
            "test_stream": async_callback,
        },
    ):
        # Mock asyncio.iscoroutinefunction to return True
        with patch("asyncio.iscoroutinefunction", return_value=True):
            # Mock the async callback execution
            with patch("asyncio.create_task") as mock_create_task:
                # Simulate processing a message
                client._on_message(
                    {
                        "stream": "test_stream",
                        "data": {"test": "data"},
                    },
                )

                # Verify create_task was called
                assert mock_create_task.called
