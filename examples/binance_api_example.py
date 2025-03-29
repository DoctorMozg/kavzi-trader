#!/usr/bin/env python3
"""
Binance API Usage Example

This script demonstrates how to use the Binance API client and WebSocket client
to interact with the Binance exchange.
"""

import logging
import os
import sys
import time
from pathlib import Path

# Import our Binance client implementations
from src.api.binance import BinanceClient, BinanceWebsocketClient

# Load environment variables and set up logging
from src.api.binance.schemas.data_dicts import KlineData, TickerData, TradeData
from src.commons.logging import setup_logging

# Add src to path to allow imports from src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Initialize logger
logger = setup_logging(name="binance_example")


def print_section(title: str) -> None:
    """Print a section title."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")


def handle_kline_message(msg: KlineData) -> None:
    """Handle kline message from WebSocket."""
    logger.info(
        f"Received kline data: Symbol={msg['s']}, "
        f"Interval={msg['k']['i']}, "
        f"Close Price={msg['k']['c']}, "
        f"Volume={msg['k']['v']}",
    )


def handle_trade_message(msg: TradeData) -> None:
    """Handle trade message from WebSocket."""
    logger.info(
        f"Received trade: Symbol={msg['s']}, "
        f"Price={msg['p']}, "
        f"Quantity={msg['q']}",
    )


def handle_ticker_message(msg: TickerData) -> None:
    """Handle ticker message from WebSocket."""
    logger.info(
        f"Received ticker: Symbol={msg['s']}, "
        f"Price Change={msg['p']}, "
        f"24h Volume={msg['v']}",
    )


def ping_example(client: BinanceClient) -> None:
    """Ping example."""
    ping_result = client.ping()
    print(f"Ping result: {ping_result}")


def get_exchange_info_example(client: BinanceClient) -> None:
    """Get exchange info example."""
    exchange_info = client.get_exchange_info()
    print(f"Number of symbols: {len(exchange_info['symbols'])}")


def get_ticker_example(client: BinanceClient) -> None:
    """Get ticker example."""
    ticker = client.get_ticker("BTCUSDT")
    print(
        f"BTCUSDT ticker - Last price: {ticker.last_price}, "
        f"24h volume: {ticker.volume}",
    )


def get_orderbook_example(client: BinanceClient) -> None:
    """Get order book example."""
    orderbook = client.get_orderbook(symbol="BTCUSDT", limit=5)
    print("Order book for BTCUSDT:")
    print(f"Bids: {orderbook.bids[:5]}")
    print(f"Asks: {orderbook.asks[:5]}")
    print(f"Last update ID: {orderbook.last_update_id}")
    print(f"Timestamp: {orderbook.timestamp}")


def get_trades_example(client: BinanceClient) -> None:
    """Get trades example."""
    trades = client.get_recent_trades(symbol="BTCUSDT", limit=10)
    print("Recent trades for BTCUSDT:")
    for trade in trades[:5]:
        print(
            f"  Trade ID: {trade.id}, Price: {trade.price}, Quantity: {trade.qty}, "
            f"Time: {trade.time}",
        )

    # Get aggregate trades
    agg_trades = client.get_agg_trades(symbol="BTCUSDT", limit=10)
    print("\nAggregate trades for BTCUSDT:")
    for trade in agg_trades[:5]:
        print(
            f"  Agg Trade ID: {trade.id}, Price: {trade.price}, "
            f"Quantity: {trade.qty}, Time: {trade.time}, "
            f"First ID: {trade.first_trade_id}",
        )
        print(f"  Last ID: {trade.last_trade_id}")


def get_klines_example(client: BinanceClient) -> None:
    """Get candlestick data example."""
    candles = client.get_klines(symbol="BTCUSDT", interval="1h", limit=5)
    print("Candlesticks for BTCUSDT:")
    for i, candle in enumerate(candles[:5], 1):
        print(
            f"Candle {i}: Open={candle.open_price}, "
            f"Close={candle.close_price}, Volume={candle.volume}",
        )


def get_account_example(client: BinanceClient) -> None:
    """Get account information example."""
    if not client.api_key or not client.api_secret:
        print("Skipping account examples as no API credentials provided")
        return

    try:
        # Get account information
        logger.info("Getting account information...")
        account_info = client.get_account_info()
        logger.info(f"Account status: {account_info['canTrade']}")

        # Get asset balance
        logger.info("Getting BTC balance...")
        btc_balance = client.get_asset_balance("BTC")
        logger.info(f"BTC balance: {btc_balance}")

    except Exception:
        logging.exception("Error in account operations")


def websocket_example() -> None:
    """Demonstrate WebSocket API usage."""
    print_section("WebSocket API Example")

    # Create a WebSocket client
    ws_client = BinanceWebsocketClient(testnet=True)

    try:
        # Start the WebSocket manager
        ws_client.start()

        # Subscribe to kline stream
        logger.info("Subscribing to BTCUSDT kline stream...")
        ws_client.subscribe_kline_stream(
            "BTCUSDT",
            "1m",
            handle_kline_message,
        )

        # Subscribe to trade stream
        logger.info("Subscribing to ETHUSDT trade stream...")
        ws_client.subscribe_trades_stream("ETHUSDT", handle_trade_message)

        # Subscribe to ticker stream
        logger.info("Subscribing to BNBUSDT ticker stream...")
        ws_client.subscribe_ticker_stream("BNBUSDT", handle_ticker_message)

        # List active streams
        active_streams = ws_client.list_active_streams()
        logger.info(f"Active streams: {active_streams}")

        # Keep the WebSocket connection alive for a few seconds
        logger.info("Waiting for messages... (Press Ctrl+C to exit)")
        time.sleep(10)  # Reduced to 10 seconds for demo purposes

    except Exception:
        logging.exception("Error in WebSocket client")
    finally:
        # Clean up WebSocket connections
        logger.info("Unsubscribing from all streams...")
        ws_client.unsubscribe_all_streams()
        logger.info("WebSocket example completed")


def main() -> None:
    """Main entry point."""
    # Initialize client
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    client = BinanceClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,  # Use testnet for examples
    )

    # Run examples
    ping_example(client)
    get_exchange_info_example(client)
    get_orderbook_example(client)
    get_trades_example(client)
    get_klines_example(client)
    get_ticker_example(client)
    get_account_example(client)

    # Run websocket example
    websocket_example()


if __name__ == "__main__":
    # Run the examples
    main()
