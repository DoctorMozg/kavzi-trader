"""
Tests for Binance API client.

This module contains tests for the Binance API client implementation.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.exceptions import APIError
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.commons.time_utility import utc_now


async def test_ping(binance_testnet_client: BinanceClient) -> None:
    """Test ping functionality."""
    result = await binance_testnet_client.ping()
    assert result


async def test_server_time(binance_testnet_client: BinanceClient) -> None:
    """Test server time functionality."""
    result = await binance_testnet_client.get_server_time()
    assert "serverTime" in result
    server_time = datetime.fromtimestamp(result["serverTime"] / 1000, UTC)
    # Server time should be within 10 seconds of local time
    local_time = utc_now()
    assert abs((server_time - local_time).total_seconds()) < 10


async def test_get_exchange_info(binance_testnet_client: BinanceClient) -> None:
    """Test exchange info functionality."""
    info = await binance_testnet_client.get_exchange_info()
    assert "symbols" in info
    assert len(info["symbols"]) > 0


async def test_get_symbol_info(binance_testnet_client: BinanceClient) -> None:
    """Test symbol info functionality."""
    info = await binance_testnet_client.get_symbol_info("BTCUSDT")
    assert info.symbol == "BTCUSDT"
    assert info.base_asset == "BTC"
    assert info.quote_asset == "USDT"


async def test_get_orderbook(binance_testnet_client: BinanceClient) -> None:
    """Test orderbook functionality."""
    orderbook = await binance_testnet_client.get_orderbook("BTCUSDT", limit=5)
    assert len(orderbook.bids) == 5
    assert len(orderbook.asks) == 5
    assert orderbook.last_update_id is not None
    assert orderbook.timestamp is not None


async def test_get_recent_trades(binance_testnet_client: BinanceClient) -> None:
    """Test recent trades functionality."""
    trades = await binance_testnet_client.get_recent_trades("BTCUSDT", limit=10)
    assert len(trades) == 10
    assert isinstance(trades[0].id, int)
    assert isinstance(trades[0].price, Decimal)
    assert isinstance(trades[0].qty, Decimal)
    assert isinstance(trades[0].time, datetime)


async def test_get_agg_trades(binance_testnet_client: BinanceClient) -> None:
    """Test aggregate trades functionality."""
    agg_trades = await binance_testnet_client.get_agg_trades("BTCUSDT", limit=10)
    assert len(agg_trades) == 10
    assert isinstance(agg_trades[0].id, int)
    assert isinstance(agg_trades[0].price, Decimal)
    assert isinstance(agg_trades[0].qty, Decimal)
    assert isinstance(agg_trades[0].time, datetime)
    assert isinstance(agg_trades[0].first_trade_id, int)
    assert isinstance(agg_trades[0].last_trade_id, int)


async def test_get_klines(binance_testnet_client: BinanceClient) -> None:
    """Test klines functionality."""
    # Get klines for the last day
    end_time = utc_now()
    start_time = end_time - timedelta(days=1)

    klines = await binance_testnet_client.get_klines(
        symbol="BTCUSDT",
        interval="1h",
        start_time=start_time,
        end_time=end_time,
        limit=24,
    )

    assert len(klines) > 0
    assert all(isinstance(k, CandlestickSchema) for k in klines)

    # Check the first kline
    first_kline = klines[0]
    assert isinstance(first_kline.open_time, datetime)
    assert isinstance(first_kline.close_time, datetime)
    assert isinstance(first_kline.open_price, Decimal)
    assert isinstance(first_kline.high_price, Decimal)
    assert isinstance(first_kline.low_price, Decimal)
    assert isinstance(first_kline.close_price, Decimal)
    assert isinstance(first_kline.volume, Decimal)
    assert isinstance(first_kline.quote_volume, Decimal)
    assert isinstance(first_kline.trades_count, int)
    assert first_kline.interval == "1h"
    assert first_kline.symbol == "BTCUSDT"


async def test_get_ticker(binance_testnet_client: BinanceClient) -> None:
    """Test ticker functionality."""
    ticker = await binance_testnet_client.get_ticker("BTCUSDT")
    assert ticker.symbol == "BTCUSDT"
    assert isinstance(ticker.last_price, Decimal)
    assert isinstance(ticker.volume, Decimal)


async def test_get_all_tickers(binance_testnet_client: BinanceClient) -> None:
    """Test all tickers functionality."""
    tickers = await binance_testnet_client.get_all_tickers()
    assert len(tickers) > 0
    assert all(hasattr(t, "symbol") for t in tickers)
    assert all(hasattr(t, "last_price") for t in tickers)


async def test_create_test_order(binance_testnet_client: BinanceClient) -> None:
    """Test creating a test order."""
    # Skip if no API credentials
    if not binance_testnet_client.api_key or not binance_testnet_client.api_secret:
        pytest.skip("No API credentials available")

    test_order = await binance_testnet_client.create_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("0.001"),
        price=Decimal(20000),
        time_in_force="GTC",
        test=True,
    )

    assert test_order.symbol == "BTCUSDT"
    assert test_order.status.value == "NEW"


async def test_order_helpers(binance_testnet_client: BinanceClient) -> None:
    """Test order helper methods."""
    # Skip if no API credentials
    if not binance_testnet_client.api_key or not binance_testnet_client.api_secret:
        pytest.skip("No API credentials available")

    # Test limit buy
    test_limit_buy = await binance_testnet_client.create_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("0.001"),
        price=Decimal(20000),
        time_in_force="GTC",
        test=True,
    )
    assert test_limit_buy.side.value == "BUY"
    assert test_limit_buy.type.value == "LIMIT"

    # Test limit sell
    test_limit_sell = await binance_testnet_client.create_order(
        symbol="BTCUSDT",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("0.001"),
        price=Decimal(50000),
        time_in_force="GTC",
        test=True,
    )
    assert test_limit_sell.side.value == "SELL"
    assert test_limit_sell.type.value == "LIMIT"

    # Test market buy
    test_market_buy = await binance_testnet_client.create_order(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("0.001"),
        test=True,
    )
    assert test_market_buy.side.value == "BUY"
    assert test_market_buy.type.value == "MARKET"

    # Test market sell
    test_market_sell = await binance_testnet_client.create_order(
        symbol="BTCUSDT",
        side="SELL",
        order_type="MARKET",
        quantity=Decimal("0.001"),
        test=True,
    )
    assert test_market_sell.side.value == "SELL"
    assert test_market_sell.type.value == "MARKET"


async def test_invalid_symbol(binance_testnet_client: BinanceClient) -> None:
    """Test error handling for invalid symbols."""
    with pytest.raises(APIError):
        await binance_testnet_client.get_symbol_info("INVALID_SYMBOL")


async def test_invalid_interval(binance_testnet_client: BinanceClient) -> None:
    """Test error handling for invalid intervals."""
    with pytest.raises(ValueError):
        await binance_testnet_client.get_klines("BTCUSDT", "INVALID_INTERVAL")
