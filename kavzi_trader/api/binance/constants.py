"""
Constants for Binance API.

This module defines constants used by the Binance API connector.
"""

# Spot API URLs
BINANCE_API_URL: str = "https://api.binance.com"
BINANCE_API_TESTNET_URL: str = "https://testnet.binance.vision"
BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws"
BINANCE_WS_TESTNET_URL: str = "wss://testnet.binance.vision/ws"

# Futures API URLs
BINANCE_FUTURES_API_URL: str = "https://fapi.binance.com"
BINANCE_FUTURES_TESTNET_URL: str = "https://testnet.binancefuture.com"
BINANCE_FUTURES_WS_URL: str = "wss://fstream.binance.com/ws"
BINANCE_FUTURES_WS_TESTNET_URL: str = "wss://stream.binancefuture.com/ws"

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

# Error codes
ERROR_CODE_INVALID_API_KEY = -2015  # API-key format invalid
ERROR_CODE_UNAUTHORIZED = -2014  # API-key has no permission for the request
ERROR_CODE_RATE_LIMIT_EXCEEDED = -1429  # Rate limit exceeded
