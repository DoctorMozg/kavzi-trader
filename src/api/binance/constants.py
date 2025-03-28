"""
Constants for Binance API.

This module defines constants used by the Binance API connector.
"""

from typing import Literal

# API URLs
BINANCE_API_URL: str = "https://api.binance.com"
BINANCE_API_TESTNET_URL: str = "https://testnet.binance.vision"
BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws"
BINANCE_WS_TESTNET_URL: str = "wss://testnet.binance.vision/ws"

# Rate limits
RATE_LIMITS: dict[str, dict[str, int]] = {
    # Weight-based limits
    "weight": {
        "minute": 1200,  # 1200 weight per minute
    },
    # Order rate limits
    "orders": {
        "second": 50,  # 50 orders per second
        "day": 160000,  # 160000 orders per day
    },
    # Raw requests limits
    "raw_requests": {
        "minute": 6000,  # 6000 raw requests per minute
    },
}

# API endpoints
ENDPOINTS: dict[str, dict[str, str]] = {
    # Public endpoints (no API key required)
    "public": {
        "ping": "/api/v3/ping",
        "time": "/api/v3/time",
        "exchange_info": "/api/v3/exchangeInfo",
        "depth": "/api/v3/depth",
        "trades": "/api/v3/trades",
        "historical_trades": "/api/v3/historicalTrades",
        "agg_trades": "/api/v3/aggTrades",
        "klines": "/api/v3/klines",
        "avg_price": "/api/v3/avgPrice",
        "ticker_24hr": "/api/v3/ticker/24hr",
        "ticker_price": "/api/v3/ticker/price",
        "ticker_book_ticker": "/api/v3/ticker/bookTicker",
    },
    # Account endpoints (requires API key)
    "account": {
        "order": "/api/v3/order",
        "test_order": "/api/v3/order/test",
        "open_orders": "/api/v3/openOrders",
        "all_orders": "/api/v3/allOrders",
        "account": "/api/v3/account",
        "my_trades": "/api/v3/myTrades",
    },
    # User data stream endpoints
    "user_data": {
        "create_listen_key": "/api/v3/userDataStream",
        "keep_alive_listen_key": "/api/v3/userDataStream",
        "close_listen_key": "/api/v3/userDataStream",
    },
}

# Kline/Candlestick intervals
KLINE_INTERVALS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1M": 2592000,
}

# Order types
ORDER_TYPES: list[
    Literal[
        "LIMIT",
        "MARKET",
        "STOP_LOSS",
        "STOP_LOSS_LIMIT",
        "TAKE_PROFIT",
        "TAKE_PROFIT_LIMIT",
        "LIMIT_MAKER",
    ]
] = [
    "LIMIT",
    "MARKET",
    "STOP_LOSS",
    "STOP_LOSS_LIMIT",
    "TAKE_PROFIT",
    "TAKE_PROFIT_LIMIT",
    "LIMIT_MAKER",
]

# Time in force
TIME_IN_FORCE: list[Literal["GTC", "IOC", "FOK"]] = [
    "GTC",  # Good Till Canceled
    "IOC",  # Immediate or Cancel
    "FOK",  # Fill or Kill
]

# Order status
ORDER_STATUS: list[
    Literal[
        "NEW",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELED",
        "PENDING_CANCEL",
        "REJECTED",
        "EXPIRED",
    ]
] = [
    "NEW",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELED",
    "PENDING_CANCEL",
    "REJECTED",
    "EXPIRED",
]

# Order side
ORDER_SIDE: list[Literal["BUY", "SELL"]] = [
    "BUY",
    "SELL",
]
