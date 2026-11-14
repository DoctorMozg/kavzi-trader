"""
Binance REST API client implementation.

Composes the endpoint groups (market data, trades, account, orders, futures
data) over a single python-binance async client.
"""

import logging

from binance.async_client import AsyncClient as BinanceAPIClient

from kavzi_trader.api.binance.account_api import AccountApi
from kavzi_trader.api.binance.futures_data_api import FuturesDataApi
from kavzi_trader.api.binance.market_data_api import MarketDataApi
from kavzi_trader.api.binance.orders_api import OrdersApi
from kavzi_trader.api.binance.trades_api import TradesApi

logger = logging.getLogger(__name__)


class BinanceClient(MarketDataApi, TradesApi, AccountApi, OrdersApi, FuturesDataApi):
    """
    Client for interacting with the Binance API.

    This class wraps the python-binance library to provide a consistent
    interface with the rest of our application, handling serialization,
    error mapping, and data conversion.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout_s: int = 30,
        proxies: dict[str, str] | None = None,
        show_limit_usage: bool = False,
    ) -> None:
        """
        Initialize the Binance client.

        Args:
            api_key: API key for authenticated endpoints
            api_secret: API secret for authenticated endpoints
            timeout_s: Request timeout in seconds
            proxies: Proxy configuration for requests
            show_limit_usage: Whether to log rate limit usage
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout_s = timeout_s
        self.show_limit_usage = show_limit_usage

        # Initialize the python-binance client
        # Note: python-binance Client doesn't accept 'timeout' directly
        requests_params: dict[str, object] = {}
        if proxies:
            requests_params["proxies"] = proxies
        if timeout_s:
            requests_params["timeout"] = timeout_s

        self.client = BinanceAPIClient(
            api_key=api_key,
            api_secret=api_secret,
            requests_params=requests_params or None,
        )

        logger.info("Initialized Binance client, timeout_s=%s", timeout_s)

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        await self.client.close_connection()
