"""
Tests for Binance WebSocket client implementation.
"""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kavzi_trader.api.binance.schemas.data_dicts import KlineData, TickerData, TradeData
from kavzi_trader.api.binance.websocket.client import BinanceWebsocketClient
from kavzi_trader.api.binance.websocket.handlers.depth import DepthStreamHandler
from kavzi_trader.api.binance.websocket.handlers.klines import KlineStreamHandler
from kavzi_trader.api.binance.websocket.handlers.ticker import TickerStreamHandler
from kavzi_trader.api.binance.websocket.handlers.trades import TradeStreamHandler
from kavzi_trader.api.binance.websocket.handlers.user_data import UserDataStreamHandler
from kavzi_trader.api.binance.websocket.stream_manager import StreamManager

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


@pytest.mark.asyncio()
async def test_start_stop(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test start and stop methods."""
    # Make start method awaitable
    mock_stream_manager.start = AsyncMock()

    # Make stop method awaitable
    mock_stream_manager.stop = AsyncMock()

    # Test start
    await websocket_client.start()
    mock_stream_manager.start.assert_called_once()

    # Test stop
    await websocket_client.stop()
    mock_stream_manager.stop.assert_called_once()


@pytest.mark.asyncio()
async def test_kline_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a kline stream."""
    # Mock the handler's subscribe method
    websocket_client.kline_handler.subscribe = AsyncMock(  # type: ignore
        return_value="btcusdt@kline_1m",
    )  # type: ignore

    # Mock callback function
    async def callback_async(data: KlineData) -> None:
        pass

    # Subscribe to kline stream
    stream_name = await websocket_client.subscribe_kline_stream(
        "BTCUSDT",
        "1m",
        callback_async,
    )

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.kline_handler.subscribe.assert_called_once_with(
        symbol="BTCUSDT",
        callback=callback_async,
        interval="1m",
    )

    # Verify the stream name was returned
    assert stream_name == "btcusdt@kline_1m"


@pytest.mark.asyncio()
async def test_ticker_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a ticker stream."""
    # Mock the handler's subscribe method
    websocket_client.ticker_handler.subscribe = AsyncMock(return_value="ethusdt@ticker")  # type: ignore

    # Mock callback function
    async def callback_async(data: TickerData) -> None:
        pass

    # Subscribe to ticker stream
    stream_name = await websocket_client.subscribe_ticker_stream(
        "ETHUSDT",
        callback_async,
    )

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.ticker_handler.subscribe.assert_called_once_with(
        symbol="ETHUSDT",
        callback=callback_async,
    )

    # Verify the stream name was returned
    assert stream_name == "ethusdt@ticker"


@pytest.mark.asyncio()
async def test_trades_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a trades stream."""
    # Mock the handler's subscribe method
    websocket_client.trade_handler.subscribe = AsyncMock(return_value="adausdt@trade")  # type: ignore

    # Mock callback function
    async def callback_async(data: TradeData) -> None:
        pass

    # Subscribe to trades stream
    stream_name = await websocket_client.subscribe_trades_stream(
        "ADAUSDT",
        callback_async,
    )

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.trade_handler.subscribe.assert_called_once_with(
        symbol="ADAUSDT",
        callback=callback_async,
    )

    # Verify the stream name was returned
    assert stream_name == "adausdt@trade"


@pytest.mark.asyncio()
async def test_depth_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a depth stream."""
    # Mock the handler's subscribe method
    websocket_client.depth_handler.subscribe = AsyncMock(return_value="bnbusdt@depth10")  # type: ignore

    # Mock callback function
    async def callback_async(data: dict[str, Any]) -> None:
        pass

    # Subscribe to depth stream
    stream_name = await websocket_client.subscribe_depth_stream(
        "BNBUSDT",
        callback_async,
        depth=10,
    )

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.depth_handler.subscribe.assert_called_once_with(
        symbol="BNBUSDT",
        callback=callback_async,
        depth=10,
    )

    # Verify the stream name was returned
    assert stream_name == "bnbusdt@depth10"


@pytest.mark.asyncio()
async def test_user_data_stream(websocket_client: BinanceWebsocketClient) -> None:
    """Test subscribing to a user data stream."""
    # Mock the handler's subscribe method
    websocket_client.user_data_handler.subscribe = AsyncMock(  # type: ignore
        return_value="user-data-stream",
    )

    # Mock callback function
    async def callback_async(data: dict[str, Any]) -> None:
        pass

    # Subscribe to user data stream
    stream_name = await websocket_client.subscribe_user_data_stream(callback_async)

    # Verify the handler's subscribe method was called with correct parameters
    websocket_client.user_data_handler.subscribe.assert_called_once_with(
        callback=callback_async,
    )

    # Verify the stream name was returned
    assert stream_name == "user-data-stream"


@pytest.mark.asyncio()
async def test_multiplex_streams(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test subscribing to multiple streams at once."""

    # Mock callback function
    async def callback_async(data: dict[str, Any]) -> None:
        pass

    # Make start method awaitable
    mock_stream_manager.start = AsyncMock()

    # Mock the bsm.multiplex_socket method
    mock_stream_manager.bsm = MagicMock()
    mock_stream_manager.bsm.multiplex_socket = AsyncMock(return_value=123)

    # Subscribe to multiple streams
    streams = ["btcusdt@kline_1m", "ethusdt@ticker"]
    stream_name = await websocket_client.subscribe_multiplex_streams(
        streams,
        callback_async,
    )

    # Verify the stream manager was started
    mock_stream_manager.start.assert_called_once()

    # Verify the multiplex socket was started with correct parameters
    mock_stream_manager.bsm.multiplex_socket.assert_called_once()

    # Verify the stream was registered
    mock_stream_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "btcusdt@kline_1m/ethusdt@ticker"


@pytest.mark.asyncio()
async def test_unsubscribe_stream(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test unsubscribing from a stream."""
    # Make unregister_stream method awaitable
    mock_stream_manager.unregister_stream = AsyncMock()

    # Unsubscribe from a stream
    await websocket_client.unsubscribe_stream("btcusdt@kline_1m")

    # Verify the stream manager's unregister_stream method was called
    mock_stream_manager.unregister_stream.assert_called_once_with("btcusdt@kline_1m")


@pytest.mark.asyncio()
async def test_unsubscribe_all_streams(
    websocket_client: BinanceWebsocketClient,
    mock_stream_manager: MagicMock,
) -> None:
    """Test unsubscribing from all streams."""
    # Make stop method awaitable
    mock_stream_manager.stop = AsyncMock()

    # Unsubscribe from all streams
    await websocket_client.unsubscribe_all_streams()

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
def test_stream_manager_init() -> None:
    """Test StreamManager initialization."""
    # Create a patched BinanceSocketManager
    with patch(
        "kavzi_trader.api.binance.websocket.stream_manager.BinanceSocketManager",
    ) as mock_bsm_class:
        # Create a StreamManager
        manager = StreamManager(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        # Verify the BinanceSocketManager was created with correct parameters
        mock_bsm_class.assert_called_once_with(
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


@pytest.mark.asyncio()
async def test_stream_manager_start_stop() -> None:
    """Test StreamManager start and stop methods."""
    # Create a patched BinanceSocketManager
    with patch(
        "kavzi_trader.api.binance.websocket.stream_manager.BinanceSocketManager",
    ) as mock_bsm_class:
        # Create a StreamManager
        mock_bsm = mock_bsm_class.return_value
        mock_bsm.stop_socket = AsyncMock()
        manager = StreamManager()

        # Test start
        await manager.start()
        assert manager._is_running is True

        # Test stop
        await manager.stop()
        assert manager._is_running is False
        assert manager.active_streams == {}  # type: ignore
        assert manager.stream_callbacks == {}  # type: ignore


@pytest.mark.asyncio()
async def test_stream_manager_process_message() -> None:
    """Test StreamManager _process_message method."""
    # Create a patched BinanceSocketManager
    with patch(
        "kavzi_trader.api.binance.websocket.stream_manager.BinanceSocketManager",
    ):
        # Create a StreamManager with mock callbacks
        on_message_mock = MagicMock()
        on_error_mock = MagicMock()
        manager = StreamManager(
            on_message=on_message_mock,
            on_error=on_error_mock,
        )

        # Mock the _get_stream_name_from_message method
        manager._get_stream_name_from_message = MagicMock(  # type: ignore
            return_value="btcusdt@kline_1m",
        )

        # Mock a stream callback
        stream_callback_mock = AsyncMock()
        manager.stream_callbacks["btcusdt@kline_1m"] = stream_callback_mock

        # Test processing a normal message
        test_msg = {"data": "test"}
        await manager._process_message(test_msg)

        # Verify the general callback was called
        on_message_mock.assert_called_once_with(test_msg)

        # Test processing an error message
        error_msg = {"error": "test_error"}
        await manager._process_message(error_msg)

        # Verify the error callback was called
        on_error_mock.assert_called_once()


# Tests for handlers
@pytest.mark.asyncio()
async def test_base_handler_unsubscribe() -> None:
    """Test BaseStreamHandler unsubscribe method."""
    # Create a mock StreamManager
    mock_manager = MagicMock(spec=StreamManager)

    # Create a handler with the mock manager
    with patch(
        "kavzi_trader.api.binance.websocket.handlers.base.BaseStreamHandler.__abstractmethods__",
        set(),
    ):
        from kavzi_trader.api.binance.websocket.handlers.base import BaseStreamHandler

        handler = BaseStreamHandler(mock_manager)  # type: ignore

        # Test unsubscribe
        await handler.unsubscribe("test_stream")

        # Verify the manager's unregister_stream method was called
        mock_manager.unregister_stream.assert_called_once_with("test_stream")


@pytest.mark.asyncio()
async def test_kline_handler_subscribe() -> None:
    """Test KlineStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.bsm = MagicMock()
    mock_manager.bsm.kline_socket = AsyncMock(return_value=123)
    mock_manager.start = AsyncMock()  # Make start() awaitable

    # Create a handler with the mock manager
    handler = KlineStreamHandler(mock_manager)

    # Mock callback function
    async def callback_async(data: KlineData) -> None:
        pass

    # Test subscribe
    stream_name = await handler.subscribe(
        symbol="BTCUSDT",
        callback=callback_async,
        interval="1m",
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "btcusdt@kline_1m"


@pytest.mark.asyncio()
async def test_ticker_handler_subscribe() -> None:
    """Test TickerStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.bsm = MagicMock()
    mock_manager.bsm.symbol_ticker_socket = AsyncMock(return_value=123)
    mock_manager.start = AsyncMock()  # Make start() awaitable

    # Create a handler with the mock manager
    handler = TickerStreamHandler(mock_manager)

    # Mock callback function
    async def callback_async(data: TickerData) -> None:
        pass

    # Test subscribe
    stream_name = await handler.subscribe(
        symbol="ETHUSDT",
        callback=callback_async,
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "ethusdt@ticker"


@pytest.mark.asyncio()
async def test_trades_handler_subscribe() -> None:
    """Test TradeStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.bsm = MagicMock()
    mock_manager.bsm.trade_socket = AsyncMock(return_value=123)
    mock_manager.start = AsyncMock()  # Make start() awaitable

    # Create a handler with the mock manager
    handler = TradeStreamHandler(mock_manager)

    # Mock callback function
    async def callback_async(data: TradeData) -> None:
        pass

    # Test subscribe
    stream_name = await handler.subscribe(
        symbol="ADAUSDT",
        callback=callback_async,
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "adausdt@trade"


@pytest.mark.asyncio()
async def test_depth_handler_subscribe() -> None:
    """Test DepthStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.bsm = MagicMock()
    mock_manager.bsm.depth_socket = AsyncMock(return_value=123)
    mock_manager.start = AsyncMock()  # Make start() awaitable

    # Create a handler with the mock manager
    handler = DepthStreamHandler(mock_manager)

    # Mock callback function
    async def callback_async(data: dict[str, Any]) -> None:
        pass

    # Test subscribe
    stream_name = await handler.subscribe(
        symbol="BNBUSDT",
        callback=callback_async,
        depth=10,
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "bnbusdt@depth10"


@pytest.mark.asyncio()
async def test_user_data_handler_subscribe() -> None:
    """Test UserDataStreamHandler subscribe method."""
    # Create a mock StreamManager with twm attribute
    mock_manager = MagicMock()
    mock_manager.bsm = MagicMock()
    mock_manager.bsm.user_socket = AsyncMock(return_value=123)
    mock_manager.start = AsyncMock()  # Make start() awaitable

    # Create a handler with the mock manager
    handler = UserDataStreamHandler(mock_manager)

    # Mock callback function
    async def callback_async(data: dict[str, Any]) -> None:
        pass

    # Test subscribe
    stream_name = await handler.subscribe(
        callback=callback_async,
    )

    # Verify the manager's methods were called
    mock_manager.start.assert_called_once()
    mock_manager.register_stream.assert_called_once()

    # Verify the stream name was returned
    assert stream_name == "user-data-stream"
