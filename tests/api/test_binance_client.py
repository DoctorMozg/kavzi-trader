"""
Tests for Binance API client.

This module contains tests for the Binance API client implementation.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.api.binance import BinanceClient
from src.api.common.exceptions import APIError
from src.commons.time_utility import utc_now


@pytest.fixture()
def client():
    """Create a Binance client for testing."""
    return BinanceClient(testnet=True)


def test_ping(client):
    """Test ping functionality."""
    assert client.ping() is True


def test_server_time(client):
    """Test server time functionality."""
    server_time = client.get_server_time()
    assert isinstance(server_time, datetime)
    # Server time should be within 10 seconds of local time
    local_time = utc_now()
    assert abs((server_time - local_time).total_seconds()) < 10


def test_get_exchange_info(client):
    """Test exchange info functionality."""
    info = client.get_exchange_info()
    assert "symbols" in info
    assert len(info["symbols"]) > 0


def test_get_symbol_info(client):
    """Test symbol info functionality."""
    info = client.get_symbol_info("BTCUSDT")
    assert info.symbol == "BTCUSDT"
    assert info.base_asset == "BTC"
    assert info.quote_asset == "USDT"


def test_get_orderbook(client):
    """Test orderbook functionality."""
    orderbook = client.get_orderbook("BTCUSDT", limit=5)
    assert hasattr(orderbook, "bids")
    assert hasattr(orderbook, "asks")
    assert len(orderbook.bids) == 5
    assert len(orderbook.asks) == 5


def test_get_recent_trades(client):
    """Test recent trades functionality."""
    trades = client.get_recent_trades("BTCUSDT", limit=10)
    assert len(trades) == 10
    assert hasattr(trades[0], "id")
    assert hasattr(trades[0], "price")
    assert hasattr(trades[0], "qty")


def test_get_klines(client):
    """Test klines functionality."""
    # Get klines for the last day
    end_time = utc_now()
    start_time = end_time - timedelta(days=1)

    klines = client.get_klines(
        symbol="BTCUSDT",
        interval="1h",
        start_time=start_time,
        end_time=end_time,
        limit=24,
    )

    assert len(klines) > 0
    assert all(isinstance(k, client.client.Candlestick) for k in klines)


def test_get_ticker(client):
    """Test ticker functionality."""
    ticker = client.get_ticker("BTCUSDT")
    assert ticker.symbol == "BTCUSDT"
    assert isinstance(ticker.last_price, Decimal)


def test_get_all_tickers(client):
    """Test all tickers functionality."""
    tickers = client.get_all_tickers()
    assert len(tickers) > 0
    assert all(hasattr(t, "symbol") for t in tickers)


def test_get_price(client):
    """Test price functionality."""
    # Test single price
    price = client.get_price("BTCUSDT")
    assert isinstance(price, float)
    assert price > 0

    # Test all prices
    prices = client.get_price()
    assert isinstance(prices, dict)
    assert "BTCUSDT" in prices
    assert prices["BTCUSDT"] > 0


def test_invalid_symbol(client):
    """Test error handling for invalid symbols."""
    with pytest.raises(APIError):
        client.get_symbol_info("INVALID_SYMBOL")


def test_invalid_interval(client):
    """Test error handling for invalid intervals."""
    with pytest.raises(ValueError):
        client.get_klines("BTCUSDT", "INVALID_INTERVAL")
