"""
Pytest configuration for API tests.

This module contains fixtures and setup for testing the API connectors.
"""

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.api.binance.client import BinanceClient
from src.api.binance.historical.client import BinanceHistoricalDataClient
from src.api.binance.websocket.client import BinanceWebsocketClient
from src.commons.time_utility import utc_now

# Skip integration tests if no API keys are available
skip_integration = pytest.mark.skipif(
    not os.environ.get("BINANCE_TEST_API_KEY")
    or not os.environ.get("BINANCE_TEST_API_SECRET"),
    reason="Binance API credentials not available",
)


@pytest.fixture()
def binance_testnet_client() -> BinanceClient:
    """
    Create a Binance testnet client for testing.

    This client uses the testnet environment and doesn't require API keys.
    """
    return BinanceClient(testnet=True)


@pytest.fixture()
def binance_client_with_keys() -> BinanceClient:
    """
    Create a Binance client with API keys for integration testing.

    This client uses real API keys from environment variables.
    """
    api_key = os.environ.get("BINANCE_TEST_API_KEY")
    api_secret = os.environ.get("BINANCE_TEST_API_SECRET")

    if not api_key or not api_secret:
        pytest.skip("Binance API credentials not available")

    return BinanceClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,
    )


@pytest.fixture()
def mock_binance_client() -> MagicMock:
    """Create a mock Binance client for testing."""
    return MagicMock(spec=BinanceClient)


@pytest.fixture()
def mock_stream_manager() -> Generator[MagicMock, None, None]:
    """Create a mock StreamManager for testing."""
    with patch("src.api.binance.websocket.stream_manager.StreamManager") as mock_class:
        mock_manager = mock_class.return_value
        mock_manager._lock = MagicMock()  # Mock the lock for testing
        mock_manager.twm = MagicMock()  # Mock the ThreadedWebsocketManager
        yield mock_manager


@pytest.fixture()
def mock_twm() -> Generator[MagicMock, None, None]:
    """Create a mock of ThreadedWebsocketManager."""
    with patch(
        "src.api.binance.websocket.stream_manager.ThreadedWebsocketManager",
    ) as mock_twm_class:
        mock_twm = mock_twm_class.return_value
        yield mock_twm


@pytest.fixture()
def historical_client(
    mock_binance_client: MagicMock,
) -> Generator[BinanceHistoricalDataClient, None, None]:
    """Create a historical data client with mocked dependencies for testing."""
    # Use a temp directory for test outputs
    import tempfile
    from pathlib import Path

    output_dir = Path(tempfile.mkdtemp())

    with patch(
        "src.api.binance.historical.client.BinanceClient",
        return_value=mock_binance_client,
    ):
        client = BinanceHistoricalDataClient(
            testnet=True,
            output_dir=output_dir,
            max_workers=2,
            batch_size=100,
        )
        yield client

        # Clean up temp directory after test
        for file in output_dir.iterdir():
            file.unlink()
        output_dir.rmdir()


@pytest.fixture()
def websocket_client(mock_stream_manager: MagicMock) -> BinanceWebsocketClient:
    """Create a websocket client with mocked dependencies for testing."""
    with patch(
        "src.api.binance.websocket.client.StreamManager",
        return_value=mock_stream_manager,
    ):
        return BinanceWebsocketClient(testnet=True)


@pytest.fixture()
def mock_response_time() -> dict[str, int]:
    """Mock server time response."""
    return {
        "serverTime": int(utc_now().timestamp() * 1000),
    }


@pytest.fixture()
def mock_symbol_info() -> dict[str, Any]:
    """Mock symbol info response."""
    return {
        "symbol": "BTCUSDT",
        "status": "TRADING",
        "baseAsset": "BTC",
        "baseAssetPrecision": 8,
        "quoteAsset": "USDT",
        "quotePrecision": 8,
        "filters": [
            {
                "filterType": "PRICE_FILTER",
                "minPrice": "0.01000000",
                "maxPrice": "1000000.00000000",
                "tickSize": "0.01000000",
            },
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.00001000",
                "maxQty": "9000.00000000",
                "stepSize": "0.00001000",
            },
        ],
    }


@pytest.fixture()
def mock_orderbook() -> dict[str, Any]:
    """Mock orderbook response."""
    return {
        "lastUpdateId": 123456789,
        "bids": [
            ["20000.00", "1.000"],
            ["19999.00", "2.000"],
            ["19998.00", "3.000"],
        ],
        "asks": [
            ["20001.00", "1.000"],
            ["20002.00", "2.000"],
            ["20003.00", "3.000"],
        ],
    }


@pytest.fixture()
def mock_trades() -> list[dict[str, Any]]:
    """Mock trades response."""
    return [
        {
            "id": 1,
            "price": "20000.00",
            "qty": "1.000",
            "time": 1672515782136,
            "isBuyerMaker": True,
            "isBestMatch": True,
        },
        {
            "id": 2,
            "price": "20001.00",
            "qty": "0.500",
            "time": 1672515782137,
            "isBuyerMaker": False,
            "isBestMatch": True,
        },
    ]


@pytest.fixture()
def mock_klines() -> list[list[Any]]:
    """Mock klines response."""
    return [
        [
            1672515780000,  # Open time
            "20000.00",  # Open
            "20010.00",  # High
            "19990.00",  # Low
            "20005.00",  # Close
            "10.000",  # Volume
            1672515839999,  # Close time
            "200050.00",  # Quote asset volume
            100,  # Number of trades
            "5.000",  # Taker buy base asset volume
            "100025.00",  # Taker buy quote asset volume
            "0",  # Ignore
        ],
        [
            1672515840000,  # Open time
            "20005.00",  # Open
            "20020.00",  # High
            "20000.00",  # Low
            "20015.00",  # Close
            "15.000",  # Volume
            1672515899999,  # Close time
            "300150.00",  # Quote asset volume
            150,  # Number of trades
            "7.500",  # Taker buy base asset volume
            "150075.00",  # Taker buy quote asset volume
            "0",  # Ignore
        ],
    ]


@pytest.fixture()
def mock_ticker() -> dict[str, Any]:
    """Mock ticker response."""
    return {
        "symbol": "BTCUSDT",
        "priceChange": "100.00",
        "priceChangePercent": "0.5",
        "weightedAvgPrice": "20050.00",
        "prevClosePrice": "20000.00",
        "lastPrice": "20100.00",
        "lastQty": "0.005",
        "bidPrice": "20099.00",
        "bidQty": "1.000",
        "askPrice": "20101.00",
        "askQty": "1.000",
        "openPrice": "20000.00",
        "highPrice": "20200.00",
        "lowPrice": "19900.00",
        "volume": "1000.000",
        "quoteVolume": "20050000.00",
        "openTime": 1672425600000,
        "closeTime": 1672512000000,
        "firstId": 100,
        "lastId": 200,
        "count": 100,
    }


@pytest.fixture()
def mock_account() -> dict[str, Any]:
    """Mock account response."""
    return {
        "makerCommission": 10,
        "takerCommission": 10,
        "buyerCommission": 0,
        "sellerCommission": 0,
        "canTrade": True,
        "canWithdraw": True,
        "canDeposit": True,
        "updateTime": 1672515782136,
        "accountType": "SPOT",
        "balances": [
            {
                "asset": "BTC",
                "free": "1.00000000",
                "locked": "0.00000000",
            },
            {
                "asset": "USDT",
                "free": "20000.00000000",
                "locked": "0.00000000",
            },
        ],
    }


@pytest.fixture()
def mock_order_response() -> dict[str, Any]:
    """Mock order response."""
    return {
        "symbol": "BTCUSDT",
        "orderId": 12345,
        "orderListId": -1,
        "clientOrderId": "myOrder1",
        "transactTime": 1672515782136,
        "price": "20000.00000000",
        "origQty": "0.00100000",
        "executedQty": "0.00000000",
        "cummulativeQuoteQty": "0.00000000",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "BUY",
        "fills": [],
    }
