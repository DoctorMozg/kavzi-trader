#!/usr/bin/env python3
"""
Binance API Usage Example

This script demonstrates how to use the Binance API client and WebSocket client
to interact with the Binance exchange.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, TypedDict

# Import our Binance client implementations
from src.api.binance import BinanceClient, BinanceWebsocketClient
from src.api.common.exceptions import APIError
from src.api.common.models import (
    CandlestickSchema,
    OrderBookSchema,
    OrderSide,
    OrderType,
    SymbolInfoSchema,
    TickerSchema,
    TimeInForce,
    TradeSchema,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class KlineData(TypedDict):
    """Type definition for kline message data."""
    e: str  # Event type
    E: int  # Event time
    s: str  # Symbol
    k: Dict[str, Any]  # Kline data


class TradeData(TypedDict):
    """Type definition for trade message data."""
    e: str  # Event type
    E: int  # Event time
    s: str  # Symbol
    t: int  # Trade ID
    p: str  # Price
    q: str  # Quantity
    b: int  # Buyer order ID
    a: int  # Seller order ID
    T: int  # Trade time
    m: bool  # Is buyer the market maker
    M: bool  # Ignore


class TickerData(TypedDict):
    """Type definition for ticker message data."""
    e: str  # Event type
    E: int  # Event time
    s: str  # Symbol
    p: str  # Price change
    P: str  # Price change percent
    w: str  # Weighted average price
    x: str  # First trade price
    c: str  # Last price
    Q: str  # Last quantity
    b: str  # Best bid price
    B: str  # Best bid quantity
    a: str  # Best ask price
    A: str  # Best ask quantity
    o: str  # Open price
    h: str  # High price
    l: str  # Low price
    v: str  # Total traded base asset volume
    q: str  # Total traded quote asset volume
    O: int  # Statistics open time
    C: int  # Statistics close time
    F: int  # First trade ID
    L: int  # Last trade ID
    n: int  # Total number of trades


def print_section(title: str) -> None:
    """Print a section title."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")


async def handle_kline_message(msg: KlineData) -> None:
    """Handle kline message from WebSocket."""
    logger.info(
        f"Received kline data: Symbol={msg['s']}, "
        f"Interval={msg['k']['i']}, "
        f"Close Price={msg['k']['c']}, "
        f"Volume={msg['k']['v']}",
    )


async def handle_trade_message(msg: TradeData) -> None:
    """Handle trade message from WebSocket."""
    logger.info(
        f"Received trade: Symbol={msg['s']}, "
        f"Price={msg['p']}, "
        f"Quantity={msg['q']}",
    )


async def handle_ticker_message(msg: TickerData) -> None:
    """Handle ticker message from WebSocket."""
    logger.info(
        f"Received ticker: Symbol={msg['s']}, "
        f"Price Change={msg['p']}, "
        f"24h Volume={msg['v']}",
    )


async def websocket_example() -> None:
    """Demonstrate WebSocket API usage."""
    print_section("WebSocket API Example")

    # Create a WebSocket client
    ws_client = BinanceWebsocketClient(testnet=True)

    try:
        # Subscribe to kline stream
        logger.info("Subscribing to BTCUSDT kline stream...")
        await ws_client.subscribe_kline_stream("BTCUSDT", "1m", handle_kline_message)

        # Subscribe to trade stream
        logger.info("Subscribing to ETHUSDT trade stream...")
        await ws_client.subscribe_trades_stream("ETHUSDT", handle_trade_message)

        # Subscribe to ticker stream
        logger.info("Subscribing to BNBUSDT ticker stream...")
        await ws_client.subscribe_ticker_stream("BNBUSDT", handle_ticker_message)

        # List active streams
        active_streams = await ws_client.list_active_streams()
        logger.info(f"Active streams: {active_streams}")

        # Keep the WebSocket connection alive for a few seconds
        logger.info("Waiting for messages... (Press Ctrl+C to exit)")
        await asyncio.sleep(10)  # Reduced to 10 seconds for demo purposes

    except Exception as e:
        logger.error(f"Error in WebSocket client: {e}")
    finally:
        # Clean up WebSocket connections
        logger.info("Unsubscribing from all streams...")
        await ws_client.unsubscribe_all_streams()
        logger.info("WebSocket example completed")


def rest_api_example() -> None:
    """Demonstrate REST API usage."""
    print_section("REST API Example")

    # Create a client instance
    # For production, use your actual API key and secret
    # client = BinanceClient(api_key="your_api_key", api_secret="your_api_secret")
    # For testing, use the testnet
    client = BinanceClient(testnet=True)

    try:
        # Test connectivity
        logger.info("Testing connectivity...")
        ping_result = client.ping()
        logger.info(f"Ping result: {ping_result}")

        # Get server time
        logger.info("Getting server time...")
        server_time = client.get_server_time()
        logger.info(f"Server time: {server_time}")

        # Get exchange information
        logger.info("Getting exchange information...")
        exchange_info = client.get_exchange_info()
        logger.info(f"Number of symbols: {len(exchange_info['symbols'])}")

        # Get symbol information for Bitcoin
        logger.info("Getting symbol information for BTCUSDT...")
        btc_info: SymbolInfoSchema = client.get_symbol_info("BTCUSDT")
        logger.info(
            f"BTCUSDT info: Base asset={btc_info.base_asset}, "
            f"Quote asset={btc_info.quote_asset}",
        )

        # Get order book
        logger.info("Getting order book for BTCUSDT...")
        orderbook: OrderBookSchema = client.get_orderbook("BTCUSDT", limit=5)
        logger.info(
            f"Order book - Top bid: {orderbook.bids[0].price}, "
            f"Top ask: {orderbook.asks[0].price}",
        )

        # Get recent trades
        logger.info("Getting recent trades for BTCUSDT...")
        trades: List[TradeSchema] = client.get_recent_trades("BTCUSDT", limit=5)
        logger.info(f"Recent trades: {len(trades)} trades fetched")
        for i, trade in enumerate(trades[:3], 1):
            logger.info(f"Trade {i}: Price={trade.price}, Quantity={trade.qty}")

        # Get candlestick data
        logger.info("Getting candlestick data for BTCUSDT...")
        candles: List[CandlestickSchema] = client.get_klines(
            symbol="BTCUSDT",
            interval="1h",
            limit=5,
        )
        logger.info(f"Candlesticks: {len(candles)} candles fetched")
        for i, candle in enumerate(candles[:3], 1):
            logger.info(
                f"Candle {i}: Open={candle.open_price}, "
                f"Close={candle.close_price}, Volume={candle.volume}",
            )

        # Get ticker for a specific symbol
        logger.info("Getting ticker for BTCUSDT...")
        ticker: TickerSchema = client.get_ticker("BTCUSDT")
        logger.info(
            f"Ticker - Last price: {ticker.last_price}, "
            f"24h Volume: {ticker.volume}",
        )

        # Get all tickers
        logger.info("Getting all tickers...")
        all_tickers: List[TickerSchema] = client.get_all_tickers()
        logger.info(f"All tickers: {len(all_tickers)} tickers fetched")
        
        # If API key is available, show how to access account info
        if client.api_key:
            try:
                # Get account information
                logger.info("Getting account information...")
                account_info = client.get_account_info()
                logger.info(f"Account status: {account_info['canTrade']}")
                
                # Get asset balance
                logger.info("Getting BTC balance...")
                btc_balance = client.get_asset_balance("BTC")
                logger.info(f"BTC balance: {btc_balance}")
                
                # Create a test order
                logger.info("Creating a test order...")
                test_order = client.create_order(
                    symbol="BTCUSDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=Decimal("0.001"),
                    price=Decimal("30000"),
                    time_in_force=TimeInForce.GTC,
                    test=True,  # Test order only
                )
                logger.info(f"Test order created")
                
                # Get open orders
                logger.info("Getting open orders...")
                open_orders = client.get_open_orders(symbol="BTCUSDT")
                logger.info(f"Open orders: {len(open_orders)}")
                
            except APIError as e:
                logger.warning(f"Account API operations failed: {e}")
                logger.warning("This is expected if you don't have a valid API key.")
        else:
            logger.info("Skipping account operations (API key not provided)")

    except Exception as e:
        logger.error(f"Error in REST API: {e}")


def order_operations_example() -> None:
    """Demonstrate order operations (testnet only)."""
    print_section("Order Operations Example (Testnet)")
    
    # Check if we have API keys for testnet
    api_key = os.environ.get("BINANCE_TESTNET_API_KEY")
    api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET")
    
    if not api_key or not api_secret:
        logger.warning("Testnet API keys not available in environment variables.")
        logger.warning("Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET")
        logger.warning("Skipping order operations example.")
        return
    
    # Create a client instance with testnet API keys
    client = BinanceClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,
    )
    
    try:
        # Check account status
        account = client.get_account_info()
        logger.info(f"Account status: canTrade={account['canTrade']}")
        
        # Get BTC balance before order
        btc_balance = client.get_asset_balance("BTC")
        logger.info(f"Initial BTC balance: Free={btc_balance['free']}, Locked={btc_balance['locked']}")
        
        # Create a limit buy order
        symbol = "BTCUSDT"
        side = OrderSide.BUY
        order_type = OrderType.LIMIT
        quantity = Decimal("0.001")  # Small amount for testing
        
        # Get current price to set a reasonable limit price
        ticker = client.get_ticker(symbol)
        current_price = Decimal(ticker.last_price)
        
        # Set limit price below current price (for buy order)
        limit_price = current_price * Decimal("0.95")  # 5% below current price
        logger.info(f"Current price: {current_price}, Setting limit price: {limit_price}")
        
        # Create the order
        order = client.create_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=limit_price,
            time_in_force=TimeInForce.GTC,
        )
        
        logger.info(f"Order created: ID={order.order_id}, Status={order.status}")
        
        # Check open orders
        open_orders = client.get_open_orders(symbol=symbol)
        logger.info(f"Open orders count: {len(open_orders)}")
        
        # Wait a moment before canceling
        logger.info("Waiting 3 seconds before canceling order...")
        time.sleep(3)
        
        # Cancel the order
        canceled_order = client.cancel_order(
            symbol=symbol,
            order_id=order.order_id,
        )
        
        logger.info(f"Order canceled: ID={canceled_order.order_id}, Status={canceled_order.status}")
        
        # Verify no open orders
        open_orders = client.get_open_orders(symbol=symbol)
        logger.info(f"Open orders after cancellation: {len(open_orders)}")
        
        # Get BTC balance after operations
        btc_balance = client.get_asset_balance("BTC")
        logger.info(f"Final BTC balance: Free={btc_balance['free']}, Locked={btc_balance['locked']}")
        
    except Exception as e:
        logger.error(f"Error in order operations: {e}")


async def main() -> None:
    """Run the example."""
    try:
        # REST API examples
        rest_api_example()
        
        # Order operations example (testnet only, if API keys available)
        order_operations_example()
        
        # WebSocket example
        await websocket_example()
        
    except KeyboardInterrupt:
        logger.info("Example interrupted by user")
    except Exception as e:
        logger.error(f"Error in examples: {e}")


if __name__ == "__main__":
    # Load environment variables if needed
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    # Run the examples
    asyncio.run(main())
