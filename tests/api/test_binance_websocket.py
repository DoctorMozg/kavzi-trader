"""
Tests for Binance WebSocket client implementation.
"""

import logging
from collections.abc import Callable, Generator
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.api.binance.schemas.callback import KlineData, TickerData, TradeData
from src.api.binance.websocket import BinanceWebsocketClient

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture()
def mock_twm() -> Generator[MagicMock, None, None]:
    """Create a mock of ThreadedWebsocketManager."""
    with patch("src.api.binance.websocket.ThreadedWebsocketManager") as mock_twm_class:
        mock_twm = mock_twm_class.return_value
        yield mock_twm


@pytest.fixture()
def ws_client(mock_twm: MagicMock) -> BinanceWebsocketClient:
    """Create a Binance websocket client with mocked dependencies."""
    return BinanceWebsocketClient(testnet=True)


def test_kline_stream(ws_client: BinanceWebsocketClient, mock_twm: MagicMock) -> None:
    """Test subscribing to a kline stream."""
    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[KlineData], None], callback_mock)

    # Subscribe to kline stream
    stream_name = ws_client.subscribe_kline_stream("BTCUSDT", "1m", callback)

    # Verify ThreadedWebsocketManager was started
    mock_twm.start.assert_called_once()

    # Verify the kline socket was started with correct parameters
    mock_twm.start_kline_socket.assert_called_once()
    args, kwargs = mock_twm.start_kline_socket.call_args
    assert kwargs["symbol"] == "BTCUSDT"
    assert kwargs["interval"] == "1m"

    # Verify stream is tracked in active_streams
    assert stream_name in ws_client.active_streams

    # Test message processing
    handler = kwargs["callback"]
    test_data = {
        "e": "kline",
        "s": "BTCUSDT",
        "k": {"i": "1m", "c": "50000", "v": "10.5"},
    }

    # Call the handler and verify callback was called
    handler(test_data)
    callback_mock.assert_called_once_with(test_data)


def test_ticker_stream(ws_client: BinanceWebsocketClient, mock_twm: MagicMock) -> None:
    """Test subscribing to a ticker stream."""
    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[TickerData], None], callback_mock)

    # Subscribe to ticker stream
    stream_name = ws_client.subscribe_ticker_stream("ETHUSDT", callback)

    # Verify ThreadedWebsocketManager was started
    mock_twm.start.assert_called_once()

    # Verify the ticker socket was started with correct parameters
    mock_twm.start_symbol_ticker_socket.assert_called_once()
    args, kwargs = mock_twm.start_symbol_ticker_socket.call_args
    assert kwargs["symbol"] == "ETHUSDT"

    # Verify stream is tracked in active_streams
    assert stream_name in ws_client.active_streams

    # Test message processing
    handler = kwargs["callback"]
    test_data = {
        "e": "24hrTicker",
        "s": "ETHUSDT",
        "c": "3000",
        "v": "100.5",
    }

    # Call the handler and verify callback was called
    handler(test_data)
    callback_mock.assert_called_once_with(test_data)


def test_depth_stream(ws_client: BinanceWebsocketClient, mock_twm: MagicMock) -> None:
    """Test subscribing to a depth stream."""
    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[dict[str, Any]], None], callback_mock)

    # Subscribe to depth stream
    stream_name = ws_client.subscribe_depth_stream(
        "BNBUSDT",
        callback,
        depth=10,
    )

    # Verify ThreadedWebsocketManager was started
    mock_twm.start.assert_called_once()

    # Verify the depth socket was started with correct parameters
    mock_twm.start_depth_socket.assert_called_once()
    args, kwargs = mock_twm.start_depth_socket.call_args
    assert kwargs["symbol"] == "BNBUSDT"
    assert kwargs["depth"] == 10

    # Verify stream is tracked in active_streams
    assert stream_name in ws_client.active_streams

    # Test message processing
    handler = kwargs["callback"]
    test_data = {
        "e": "depth",
        "s": "BNBUSDT",
        "b": [["300", "1.0"]],
        "a": [["301", "2.0"]],
    }

    # Call the handler and verify callback was called
    handler(test_data)
    callback_mock.assert_called_once_with(test_data)


def test_trades_stream(ws_client: BinanceWebsocketClient, mock_twm: MagicMock) -> None:
    """Test subscribing to a trades stream."""
    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[TradeData], None], callback_mock)

    # Subscribe to trades stream
    stream_name = ws_client.subscribe_trades_stream("ADAUSDT", callback)

    # Verify ThreadedWebsocketManager was started
    mock_twm.start.assert_called_once()

    # Verify the trade socket was started with correct parameters
    mock_twm.start_trade_socket.assert_called_once()
    args, kwargs = mock_twm.start_trade_socket.call_args
    assert kwargs["symbol"] == "ADAUSDT"

    # Verify stream is tracked in active_streams
    assert stream_name in ws_client.active_streams

    # Test message processing
    handler = kwargs["callback"]
    test_data = {
        "e": "trade",
        "s": "ADAUSDT",
        "p": "1.5",
        "q": "100",
    }

    # Call the handler and verify callback was called
    handler(test_data)
    callback_mock.assert_called_once_with(test_data)


def test_multiplex_streams(
    ws_client: BinanceWebsocketClient,
    mock_twm: MagicMock,
) -> None:
    """Test subscribing to multiple streams at once."""
    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[dict[str, Any]], None], callback_mock)

    # Subscribe to multiple streams
    streams = ["btcusdt@kline_1m", "ethusdt@ticker"]
    stream_name = ws_client.subscribe_multiplex_streams(streams, callback)

    # Verify ThreadedWebsocketManager was started
    mock_twm.start.assert_called_once()

    # Verify the multiplex socket was started with correct parameters
    mock_twm.start_multiplex_socket.assert_called_once()
    args, kwargs = mock_twm.start_multiplex_socket.call_args
    assert kwargs["streams"] == streams

    # Verify stream is tracked in active_streams
    assert stream_name in ws_client.active_streams

    # Test message processing
    handler = kwargs["callback"]
    test_data = {
        "stream": "btcusdt@kline_1m",
        "data": {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {"i": "1m", "c": "50000", "v": "10.5"},
        },
    }

    # Call the handler and verify callback was called
    handler(test_data)
    callback_mock.assert_called_once_with(test_data)


def test_unsubscribe_stream(
    ws_client: BinanceWebsocketClient,
    mock_twm: MagicMock,
) -> None:
    """Test unsubscribing from a stream."""
    # First subscribe to a stream
    callback_mock = MagicMock()
    callback = cast(Callable[[KlineData], None], callback_mock)

    stream_name = ws_client.subscribe_kline_stream("BTCUSDT", "1m", callback)
    assert stream_name in ws_client.active_streams

    # Now unsubscribe
    ws_client.unsubscribe_stream(stream_name)

    # Verify stop_socket was called
    mock_twm.stop_socket.assert_called_once()

    # Verify stream was removed from active_streams
    assert stream_name not in ws_client.active_streams

    # Verify callback was removed
    assert stream_name not in ws_client.stream_callbacks


def test_unsubscribe_all_streams(
    ws_client: BinanceWebsocketClient,
    mock_twm: MagicMock,
) -> None:
    """Test unsubscribing from all streams."""
    # First subscribe to multiple streams
    callback_mock = MagicMock()
    callback = cast(Callable[[KlineData | TickerData], None], callback_mock)

    ws_client.subscribe_kline_stream("BTCUSDT", "1m", callback)
    ws_client.subscribe_ticker_stream("ETHUSDT", callback)

    # Verify we have active streams
    assert len(ws_client.active_streams) > 0

    # Now unsubscribe from all
    ws_client.unsubscribe_all_streams()

    # Verify all streams were removed
    assert len(ws_client.active_streams) == 0
    assert len(ws_client.stream_callbacks) == 0


def test_error_handling() -> None:
    """Test error handling in WebSocket callbacks."""
    # Setup a mock that will receive error messages
    error_callback_mock = MagicMock()

    # Create a client with the error callback
    ws_client = BinanceWebsocketClient(
        testnet=True,
        on_error=error_callback_mock,
    )

    # Manually trigger message processing with an error message
    error_msg = {
        "error": "error",
        "m": "Test error message",
    }

    # Process the error message
    ws_client._process_message(error_msg)

    # Verify the error callback was called
    error_callback_mock.assert_called_once()
    args, _ = error_callback_mock.call_args
    assert isinstance(args[0], Exception)


def test_get_stream_name_from_message(
    ws_client: BinanceWebsocketClient,
) -> None:
    """Test extracting stream names from different message types."""
    # Test kline message
    kline_msg = {
        "e": "kline",
        "s": "BTCUSDT",
        "k": {"i": "1m"},
    }
    stream_name = ws_client._get_stream_name_from_message(kline_msg)
    assert stream_name == "btcusdt@kline_1m"

    # Test ticker message
    ticker_msg = {
        "e": "24hrTicker",
        "s": "ETHUSDT",
    }
    stream_name = ws_client._get_stream_name_from_message(ticker_msg)
    assert stream_name == "ethusdt@ticker"

    # Test trade message
    trade_msg = {
        "e": "trade",
        "s": "BNBUSDT",
    }
    stream_name = ws_client._get_stream_name_from_message(trade_msg)
    assert stream_name == "bnbusdt@trade"

    # Test depth message
    depth_msg = {
        "e": "depth",
        "s": "ADAUSDT",
    }
    stream_name = ws_client._get_stream_name_from_message(depth_msg)
    assert stream_name == "adausdt@depth"

    # Test multiplex format
    multiplex_msg = {
        "stream": "btcusdt@kline_1m",
        "data": {},
    }
    stream_name = ws_client._get_stream_name_from_message(multiplex_msg)
    assert stream_name == "btcusdt@kline_1m"
