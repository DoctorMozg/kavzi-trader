"""
Tests for Binance WebSocket client implementation.
"""

import logging
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import MagicMock, patch

from src.api.binance.schemas.data_dicts import KlineData, TickerData, TradeData
from src.api.binance.websocket.client import BinanceWebsocketClient
from src.api.binance.websocket.handlers.depth import DepthStreamHandler
from src.api.binance.websocket.handlers.klines import KlineStreamHandler
from src.api.binance.websocket.handlers.ticker import TickerStreamHandler
from src.api.binance.websocket.handlers.trades import TradeStreamHandler
from src.api.binance.websocket.handlers.user_data import UserDataStreamHandler
from src.api.binance.websocket.stream_manager import StreamManager

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_client_initialization(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test client initialization."""
    # Verify that the stream manager was created
    assert websocket_client.stream_manager == mock_stream_manager

    # Verify that the handlers were created
    assert isinstance(websocket_client.kline_handler, KlineStreamHandler)
    assert isinstance(websocket_client.ticker_handler, TickerStreamHandler)
    assert isinstance(websocket_client.trade_handler, TradeStreamHandler)
    assert isinstance(websocket_client.depth_handler, DepthStreamHandler)
    assert isinstance(websocket_client.user_data_handler, UserDataStreamHandler)


def test_start_stop(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test start and stop methods."""
    # Test start
    websocket_client.start()
    mock_stream_manager.start.assert_called_once()

    # Test stop
    websocket_client.stop()
    mock_stream_manager.stop.assert_called_once()


def test_kline_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a kline stream."""
    # Mock the handler's subscribe method
    websocket_client.kline_handler.subscribe = MagicMock(  # type: ignore
        return_value="btcusdt@kline_1m",
    )

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[KlineData], None], callback_mock)

    # Subscribe to kline stream
    stream_name = websocket_client.subscribe_kline_stream("BTCUSDT", "1m", callback)

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.kline_handler.subscribe.assert_called_once_with(
        symbol="BTCUSDT",
        callback=callback,
        interval="1m",
    )

    # Verify the stream name was returned
    assert stream_name == "btcusdt@kline_1m"


def test_ticker_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a ticker stream."""
    # Mock the handler's subscribe method
    websocket_client.ticker_handler.subscribe = MagicMock(return_value="ethusdt@ticker")  # type: ignore

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[TickerData], None], callback_mock)

    # Subscribe to ticker stream
    stream_name = websocket_client.subscribe_ticker_stream("ETHUSDT", callback)

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.ticker_handler.subscribe.assert_called_once_with(
        symbol="ETHUSDT",
        callback=callback,
    )

    # Verify the stream name was returned
    assert stream_name == "ethusdt@ticker"


def test_trades_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a trades stream."""
    # Mock the handler's subscribe method
    websocket_client.trade_handler.subscribe = MagicMock(return_value="adausdt@trade")  # type: ignore

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[TradeData], None], callback_mock)

    # Subscribe to trades stream
    stream_name = websocket_client.subscribe_trades_stream("ADAUSDT", callback)

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.trade_handler.subscribe.assert_called_once_with(
        symbol="ADAUSDT",
        callback=callback,
    )

    # Verify the stream name was returned
    assert stream_name == "adausdt@trade"


def test_depth_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a depth stream."""
    # Mock the handler's subscribe method
    websocket_client.depth_handler.subscribe = MagicMock(return_value="bnbusdt@depth10")  # type: ignore

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[dict[str, Any]], None], callback_mock)

    # Subscribe to depth stream
    stream_name = websocket_client.subscribe_depth_stream(
        "BNBUSDT",
        callback,
        depth=10,
    )

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.depth_handler.subscribe.assert_called_once_with(
        symbol="BNBUSDT",
        callback=callback,
        depth=10,
    )

    # Verify the stream name was returned
    assert stream_name == "bnbusdt@depth10"


def test_user_data_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a user data stream."""
    # Mock the handler's subscribe method
    websocket_client.user_data_handler.subscribe = MagicMock(  # type: ignore
        return_value="user-data-stream",
    )

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[dict[str, Any]], None], callback_mock)

    # Subscribe to user data stream
    stream_name = websocket_client.subscribe_user_data_stream(callback)

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.user_data_handler.subscribe.assert_called_once_with(
        callback=callback,
    )

    # Verify the stream name was returned
    assert stream_name == "user-data-stream"


def test_multiplex_streams(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test subscribing to multiple streams at once."""
    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[dict[str, Any]], None], callback_mock)

    # Mock the twm.start_multiplex_socket method
    mock_stream_manager.twm.start_multiplex_socket.return_value = 123

    # Subscribe to multiple streams
    streams = ["btcusdt@kline_1m", "ethusdt@ticker"]
    stream_name = websocket_client.subscribe_multiplex_streams(streams, callback)

    # Verify the stream manager was started
    mock_stream_manager.start.assert_called_once()

    # Verify the multiplex socket was started with correct parameters
    mock_stream_manager.twm.start_multiplex_socket.assert_called_once()
    args, kwargs = mock_stream_manager.twm.start_multiplex_socket.call_args
    assert kwargs["streams"] == streams

    # Verify the stream was registered
    mock_stream_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "btcusdt@kline_1m/ethusdt@ticker"


def test_unsubscribe_stream(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test unsubscribing from a stream."""
    # Unsubscribe from a stream
    websocket_client.unsubscribe_stream("btcusdt@kline_1m")

    # Verify the stream manager's unregister_stream method was called
    mock_stream_manager.unregister_stream.assert_called_once_with("btcusdt@kline_1m")


def test_unsubscribe_all_streams(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test unsubscribing from all streams."""
    # Unsubscribe from all streams
    websocket_client.unsubscribe_all_streams()

    # Verify the stream manager's stop method was called
    mock_stream_manager.stop.assert_called_once()


def test_list_active_streams(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test listing active streams."""
    # Mock the stream manager's list_active_streams method
    mock_stream_manager.list_active_streams.return_value = [
        "btcusdt@kline_1m",
        "ethusdt@ticker",
    ]

    # List active streams
    streams = websocket_client.list_active_streams()

    # Verify the stream manager's list_active_streams method was called
    mock_stream_manager.list_active_streams.assert_called_once()

    # Verify the streams were returned
    assert streams == ["btcusdt@kline_1m", "ethusdt@ticker"]


def test_is_connected(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test checking if the client is connected."""
    # Mock the stream manager's is_connected method
    mock_stream_manager.is_connected.return_value = True

    # Check if connected
    connected = websocket_client.is_connected()

    # Verify the stream manager's is_connected method was called
    mock_stream_manager.is_connected.assert_called_once()

    # Verify the result was returned
    assert connected is True


# Tests for StreamManager
@patch("src.api.binance.websocket.stream_manager.ThreadedWebsocketManager")
def test_stream_manager_init(mock_twm_class: MagicMock) -> None:
    """Test StreamManager initialization."""
    # Create a StreamManager
    manager = StreamManager(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )

    # Verify the ThreadedWebsocketManager was created with correct parameters
    mock_twm_class.assert_called_once_with(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )

    # Verify the manager's properties
    assert manager.api_key == "test_key"
    assert manager.api_secret == "test_secret"  # noqa: S105
    assert manager.testnet is True
    assert manager.active_streams == {}
    assert manager.stream_callbacks == {}
    assert manager._is_running is False


@patch("src.api.binance.websocket.stream_manager.ThreadedWebsocketManager")
def test_stream_manager_start_stop(mock_twm_class: MagicMock) -> None:
    """Test StreamManager start and stop methods."""
    # Create a StreamManager
    mock_twm = mock_twm_class.return_value
    manager = StreamManager()

    # Test start
    manager.start()
    mock_twm.start.assert_called_once()
    assert manager._is_running is True

    # Test stop
    manager.stop()
    mock_twm.stop.assert_called_once()
    assert manager._is_running is False
    assert manager.active_streams == {}  # type: ignore
    assert manager.stream_callbacks == {}  # type: ignore


@patch("src.api.binance.websocket.stream_manager.ThreadedWebsocketManager")
def test_stream_manager_process_message(mock_twm_class: MagicMock) -> None:
    """Test StreamManager _process_message method."""
    # Create a StreamManager with mock callbacks
    on_message_mock = MagicMock()
    on_error_mock = MagicMock()
    manager = StreamManager(
        on_message=on_message_mock,
        on_error=on_error_mock,
    )

    # Mock the _get_stream_name_from_message method
    manager._get_stream_name_from_message = MagicMock(return_value="btcusdt@kline_1m")  # type: ignore

    # Mock a stream callback
    stream_callback_mock = MagicMock()
    manager.stream_callbacks["btcusdt@kline_1m"] = stream_callback_mock

    # Test processing a normal message
    test_msg = {"data": "test"}
    manager._process_message(test_msg)

    # Verify the stream callback was called
    stream_callback_mock.assert_called_once_with(test_msg)

    # Verify the general callback was called
    on_message_mock.assert_called_once_with(test_msg)

    # Test processing an error message
    error_msg = {"error": "test_error"}
    manager._process_message(error_msg)

    # Verify the error callback was called
    on_error_mock.assert_called_once()


# Tests for handlers
def test_base_handler_unsubscribe() -> None:
    """Test BaseStreamHandler unsubscribe method."""
    # Create a mock StreamManager
    mock_manager = MagicMock(spec=StreamManager)

    # Create a handler with the mock manager
    with patch(
        "src.api.binance.websocket.handlers.base.BaseStreamHandler.__abstractmethods__",
        set(),
    ):
        from src.api.binance.websocket.handlers.base import BaseStreamHandler

        handler = BaseStreamHandler(mock_manager)  # type: ignore

        # Test unsubscribe
        handler.unsubscribe("test_stream")

        # Verify the manager's unregister_stream method was called
        mock_manager.unregister_stream.assert_called_once_with("test_stream")


def test_kline_handler_subscribe() -> None:
    """Test KlineStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.twm = MagicMock()
    mock_manager.twm.start_kline_socket.return_value = 123

    # Create a handler with the mock manager
    handler = KlineStreamHandler(mock_manager)

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[KlineData], None], callback_mock)

    # Test subscribe
    stream_name = handler.subscribe(
        symbol="BTCUSDT",
        callback=callback,
        interval="1m",
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.twm.start_kline_socket.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "btcusdt@kline_1m"


def test_ticker_handler_subscribe() -> None:
    """Test TickerStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.twm = MagicMock()
    mock_manager.twm.start_symbol_ticker_socket.return_value = 123

    # Create a handler with the mock manager
    handler = TickerStreamHandler(mock_manager)

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[TickerData], None], callback_mock)

    # Test subscribe
    stream_name = handler.subscribe(
        symbol="ETHUSDT",
        callback=callback,
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.twm.start_symbol_ticker_socket.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "ethusdt@ticker"


def test_trades_handler_subscribe() -> None:
    """Test TradeStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.twm = MagicMock()
    mock_manager.twm.start_trade_socket.return_value = 123

    # Create a handler with the mock manager
    handler = TradeStreamHandler(mock_manager)

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[TradeData], None], callback_mock)

    # Test subscribe
    stream_name = handler.subscribe(
        symbol="ADAUSDT",
        callback=callback,
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.twm.start_trade_socket.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "adausdt@trade"


def test_depth_handler_subscribe() -> None:
    """Test DepthStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.twm = MagicMock()
    mock_manager.twm.start_depth_socket.return_value = 123

    # Create a handler with the mock manager
    handler = DepthStreamHandler(mock_manager)

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[dict[str, Any]], None], callback_mock)

    # Test subscribe
    stream_name = handler.subscribe(
        symbol="BNBUSDT",
        callback=callback,
        depth=10,
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.twm.start_depth_socket.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "bnbusdt@depth10"


def test_user_data_handler_subscribe() -> None:
    """Test UserDataStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.twm = MagicMock()
    mock_manager.twm.start_user_socket.return_value = 123
    mock_manager.api_key = "test_key"
    mock_manager.api_secret = "test_secret"  # noqa: S105

    # Create a handler with the mock manager
    handler = UserDataStreamHandler(mock_manager)

    # Mock callback function
    callback_mock = MagicMock()
    callback = cast(Callable[[dict[str, Any]], None], callback_mock)

    # Test subscribe
    stream_name = handler.subscribe(
        callback=callback,
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.twm.start_user_socket.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "user-data-stream"
