"""
Binance REST API client implementation.

This module provides a client for interacting with the Binance API, wrapping the
python-binance library to fit our project's interfaces and data models.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from functools import wraps
from typing import Any, cast

from binance.async_client import AsyncClient as BinanceAPIClient
from binance.exceptions import BinanceAPIException, BinanceRequestException

from kavzi_trader.api.binance.constants import (
    ERROR_CODE_INVALID_API_KEY,
    ERROR_CODE_MARGIN_TYPE_ALREADY_SET,
    ERROR_CODE_RATE_LIMIT_EXCEEDED,
    ERROR_CODE_UNAUTHORIZED,
    KLINE_INTERVALS,
)
from kavzi_trader.api.common.exceptions import (
    APIError,
    AuthenticationError,
    ExchangeError,
    RateLimitError,
    RequestError,
)
from kavzi_trader.api.common.models import (
    CandlestickSchema,
    OrderBookEntrySchema,
    OrderBookSchema,
    OrderFillSchema,
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
    SymbolInfoSchema,
    TickerSchema,
    TimeInForce,
    TradeSchema,
)
from kavzi_trader.commons.time_utility import (
    MILLISECONDS_IN_SECOND,
    utc_now,
    utc_timestamp,
)

logger = logging.getLogger(__name__)


def handle_api_errors[T](func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to handle API errors from Binance.

    This decorator wraps a method and catches any exceptions,
    passing them to the _handle_error method before re-raising.

    Args:
        func: The function to wrap

    Returns:
        The wrapped function
    """

    @wraps(func)
    def wrapper(self, *args: Any, **kwargs: Any) -> T:  # type: ignore  # noqa: ANN001, ANN401
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            self._handle_error(e)
            raise  # This will never be reached due to _handle_error always raising

    return wrapper


class BinanceClient:
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
        timeout: int = 30,
        proxies: dict[str, str] | None = None,
        show_limit_usage: bool = False,
    ) -> None:
        """
        Initialize the Binance client.

        Args:
            api_key: API key for authenticated endpoints
            api_secret: API secret for authenticated endpoints
            timeout: Request timeout in seconds
            proxies: Proxy configuration for requests
            show_limit_usage: Whether to log rate limit usage
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.show_limit_usage = show_limit_usage

        # Initialize the python-binance client
        # Note: python-binance Client doesn't accept 'timeout' directly
        requests_params: dict[str, Any] = {}
        if proxies:
            requests_params["proxies"] = proxies
        if timeout:
            requests_params["timeout"] = timeout

        self.client = BinanceAPIClient(
            api_key=api_key,
            api_secret=api_secret,
            requests_params=requests_params or None,
        )

        logger.info("Initialized Binance client, timeout=%s", timeout)

    def _handle_error(self, error: Exception) -> None:
        """
        Handle API errors and map them to our exception types.

        Args:
            error: The exception to handle

        Raises:
            AuthenticationError: For authentication issues
            RateLimitError: For rate limit issues
            RequestError: For network or request issues
            ExchangeError: For Binance-specific errors
            APIError: For generic API errors
        """
        message = str(error)
        logger.debug("Handling API error: %s", message)

        if isinstance(error, BinanceAPIException):
            error_code = error.code

            # Authentication errors
            if error_code in (ERROR_CODE_INVALID_API_KEY, ERROR_CODE_UNAUTHORIZED):
                raise AuthenticationError(message)

            # Rate limit errors
            if error_code == ERROR_CODE_RATE_LIMIT_EXCEEDED:
                raise RateLimitError(message)

            # Exchange-specific errors
            raise ExchangeError(message, code=error_code)

        if isinstance(error, BinanceRequestException):
            raise RequestError(message)

        raise APIError(f"Unexpected error: {message}")

    @handle_api_errors
    async def ping(self) -> bool:
        """
        Test connectivity to the API.

        Returns:
            Dictionary with True on success
        """
        await self.client.ping()
        return True

    @handle_api_errors
    async def get_server_time(self) -> dict[str, int]:
        """
        Get the server time.

        Returns:
            Dictionary with {'serverTime': timestamp} in milliseconds
        """
        return cast("dict[str, int]", await self.client.get_server_time())

    @handle_api_errors
    async def get_exchange_info(self) -> dict[str, Any]:
        """
        Get exchange information including rate limits, symbol information.

        Returns:
            Exchange information
        """
        return cast("dict[str, Any]", await self.client.get_exchange_info())

    @handle_api_errors
    async def get_symbol_info(self, symbol: str) -> SymbolInfoSchema:
        """
        Get detailed information for a specific symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Symbol information
        """
        # Get all symbols and find the one we want
        exchange_info = await self.client.get_exchange_info()
        symbol_info = None

        for info in exchange_info["symbols"]:
            if info["symbol"] == symbol:
                symbol_info = info
                break

        if not symbol_info:
            raise ExchangeError(f"Symbol not found: {symbol}")

        # Extract relevant information and convert to our schema
        filters = {flt["filterType"]: flt for flt in symbol_info["filters"]}

        # Extract price filter values
        price_filter = filters.get("PRICE_FILTER", {})
        min_price = Decimal(price_filter.get("minPrice", "0"))
        max_price = Decimal(price_filter.get("maxPrice", "0"))
        tick_size = Decimal(price_filter.get("tickSize", "0"))

        # Extract lot size filter values
        lot_size = filters.get("LOT_SIZE", {})
        min_qty = Decimal(lot_size.get("minQty", "0"))
        max_qty = Decimal(lot_size.get("maxQty", "0"))
        step_size = Decimal(lot_size.get("stepSize", "0"))

        # Extract min notional
        min_notional = Decimal(
            filters.get("MIN_NOTIONAL", {}).get("minNotional", "0"),
        )

        # Create and return our schema object
        return SymbolInfoSchema(
            symbol=symbol_info["symbol"],
            status=symbol_info["status"],
            base_asset=symbol_info["baseAsset"],
            quote_asset=symbol_info["quoteAsset"],
            base_precision=symbol_info["baseAssetPrecision"],
            quote_precision=symbol_info["quoteAssetPrecision"],
            min_price=min_price,
            max_price=max_price,
            tick_size=tick_size,
            min_qty=min_qty,
            max_qty=max_qty,
            step_size=step_size,
            min_notional=min_notional,
            filters=symbol_info["filters"],
        )

    @handle_api_errors
    async def get_orderbook(self, symbol: str, limit: int = 100) -> OrderBookSchema:
        """
        Get order book for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Number of entries to return (default 100, max 5000)

        Returns:
            Order book with bids and asks
        """
        depth = await self.client.get_order_book(symbol=symbol, limit=limit)

        # Convert the response to our schema
        bids = [
            OrderBookEntrySchema(price=Decimal(b[0]), qty=Decimal(b[1]))
            for b in depth["bids"]
        ]

        asks = [
            OrderBookEntrySchema(price=Decimal(a[0]), qty=Decimal(a[1]))
            for a in depth["asks"]
        ]

        return OrderBookSchema(
            bids=bids,
            asks=asks,
            last_update_id=depth["lastUpdateId"],
            timestamp=utc_timestamp(time.time()),
        )

    @handle_api_errors
    async def get_recent_trades(
        self,
        symbol: str,
        limit: int = 500,
    ) -> list[TradeSchema]:
        """
        Get recent trades for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Number of trades to return (default 500, max 1000)

        Returns:
            List of recent trades
        """
        trades = await self.client.get_recent_trades(symbol=symbol, limit=limit)

        # Convert the response to our schema
        return [
            TradeSchema(
                id=trade["id"],
                price=Decimal(trade["price"]),
                qty=Decimal(trade["qty"]),
                time=utc_timestamp(trade["time"] / MILLISECONDS_IN_SECOND),
                is_buyer_maker=trade["isBuyerMaker"],
                is_best_match=trade.get("isBestMatch", True),
                quote_qty=Decimal(trade.get("quoteQty", "0")),
            )
            for trade in trades
        ]

    @handle_api_errors
    async def get_historical_trades(
        self,
        symbol: str,
        limit: int = 500,
        from_id: int | None = None,
        start_time: int | datetime | None = None,
    ) -> list[TradeSchema]:
        """
        Get historical trades for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Number of trades to return (default 500, max 1000)
            from_id: Trade ID to fetch from (exclusive)
            start_time: Start time for trades in milliseconds or datetime

        Returns:
            List of historical trades
        """
        # Process start_time if it's a datetime
        start_time_ms = None
        if start_time is not None:
            if isinstance(start_time, datetime):
                start_time_ms = int(start_time.timestamp() * MILLISECONDS_IN_SECOND)
            else:
                start_time_ms = start_time

        # Prepare parameters
        params = {}
        if from_id is not None:
            params["fromId"] = from_id
        if start_time_ms is not None:
            params["startTime"] = start_time_ms

        # Execute request
        trades = await self.client.get_historical_trades(
            symbol=symbol,
            limit=limit,
            **params,
        )

        # Convert the response to our schema
        return [
            TradeSchema(
                id=trade["id"],
                price=Decimal(trade["price"]),
                qty=Decimal(trade["qty"]),
                time=utc_timestamp(trade["time"] / MILLISECONDS_IN_SECOND),
                is_buyer_maker=trade["isBuyerMaker"],
                is_best_match=trade.get("isBestMatch", True),
                quote_qty=Decimal(trade.get("quoteQty", "0")),
            )
            for trade in trades
        ]

    @handle_api_errors
    async def get_agg_trades(
        self,
        symbol: str,
        from_id: int | None = None,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
        limit: int = 500,
    ) -> list[TradeSchema]:
        """
        Get compressed/aggregate trades for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            from_id: ID to get aggregate trades from (inclusive)
            start_time: Start time in milliseconds or datetime
            end_time: End time in milliseconds or datetime
            limit: Number of trades to return (default 500, max 1000)

        Returns:
            List of aggregate trades
        """
        # Process start_time and end_time if they're datetime objects
        start_time_ms = None
        if start_time is not None:
            if isinstance(start_time, datetime):
                start_time_ms = int(start_time.timestamp() * MILLISECONDS_IN_SECOND)
            else:
                start_time_ms = start_time

        end_time_ms = None
        if end_time is not None:
            if isinstance(end_time, datetime):
                end_time_ms = int(end_time.timestamp() * MILLISECONDS_IN_SECOND)
            else:
                end_time_ms = end_time

        # Prepare parameters
        params = {}
        if from_id is not None:
            params["fromId"] = from_id
        if start_time_ms is not None:
            params["startTime"] = start_time_ms
        if end_time_ms is not None:
            params["endTime"] = end_time_ms

        # Execute request
        agg_trades = await self.client.get_aggregate_trades(
            symbol=symbol,
            limit=limit,
            **params,
        )

        # Convert the response to our schema
        return [
            TradeSchema(
                id=trade["a"],  # Aggregate trade ID
                price=Decimal(trade["p"]),
                qty=Decimal(trade["q"]),
                time=utc_timestamp(trade["T"] / MILLISECONDS_IN_SECOND),
                is_buyer_maker=trade["m"],
                is_best_match=trade.get("M", True),
                first_trade_id=trade.get("f"),
                last_trade_id=trade.get("l"),
                quote_qty=Decimal(float(trade["p"]) * float(trade["q"])),
            )
            for trade in agg_trades
        ]

    @handle_api_errors
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
        limit: int = 500,
    ) -> list[CandlestickSchema]:
        """
        Get kline/candlestick data for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            interval: Kline interval (e.g., "1m", "1h", "1d")
            start_time: Start time for klines in milliseconds or datetime
            end_time: End time for klines in milliseconds or datetime
            limit: Number of klines to return (default 500, max 1000)

        Returns:
            List of klines/candlesticks
        """
        # Validate interval
        if interval not in KLINE_INTERVALS:
            valid_intervals = ", ".join(KLINE_INTERVALS.keys())
            raise ValueError(
                f"Invalid interval: {interval}. Valid intervals: {valid_intervals}",
            )

        # Process start_time and end_time if they're datetime objects
        start_time_ms = None
        if start_time is not None:
            if isinstance(start_time, datetime):
                start_time_ms = int(start_time.timestamp() * MILLISECONDS_IN_SECOND)
            else:
                start_time_ms = start_time

        end_time_ms = None
        if end_time is not None:
            if isinstance(end_time, datetime):
                end_time_ms = int(end_time.timestamp() * MILLISECONDS_IN_SECOND)
            else:
                end_time_ms = end_time

        # Prepare parameters
        params = {}
        if start_time_ms is not None:
            params["startTime"] = start_time_ms
        if end_time_ms is not None:
            params["endTime"] = end_time_ms

        # Execute request
        klines = await self.client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            **params,
        )

        # Convert the response to our schema
        return [
            CandlestickSchema(
                open_time=utc_timestamp(kline[0] / MILLISECONDS_IN_SECOND),
                open_price=Decimal(kline[1]),
                high_price=Decimal(kline[2]),
                low_price=Decimal(kline[3]),
                close_price=Decimal(kline[4]),
                volume=Decimal(kline[5]),
                close_time=utc_timestamp(kline[6] / MILLISECONDS_IN_SECOND),
                quote_volume=Decimal(kline[7]),
                trades_count=kline[8],
                taker_buy_base_volume=Decimal(kline[9]),
                taker_buy_quote_volume=Decimal(kline[10]),
                interval=interval,
                symbol=symbol,
            )
            for kline in klines
        ]

    @handle_api_errors
    async def get_ticker(self, symbol: str) -> TickerSchema:
        """
        Get 24hr ticker price change statistics for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Ticker statistics
        """
        ticker = await self.client.get_ticker(symbol=symbol)

        # Convert the response to our schema
        return TickerSchema(
            symbol=ticker["symbol"],
            last_price=Decimal(ticker["lastPrice"]),
            price_change=Decimal(ticker["priceChange"]),
            price_change_percent=Decimal(ticker["priceChangePercent"]),
            weighted_avg_price=Decimal(ticker["weightedAvgPrice"]),
            prev_close_price=Decimal(ticker["prevClosePrice"]),
            last_qty=Decimal(ticker["lastQty"]),
            bid_price=Decimal(ticker["bidPrice"]),
            bid_qty=Decimal(ticker["bidQty"]),
            ask_price=Decimal(ticker["askPrice"]),
            ask_qty=Decimal(ticker["askQty"]),
            open_price=Decimal(ticker["openPrice"]),
            high_price=Decimal(ticker["highPrice"]),
            low_price=Decimal(ticker["lowPrice"]),
            volume=Decimal(ticker["volume"]),
            quote_volume=Decimal(ticker["quoteVolume"]),
            open_time=utc_timestamp(ticker["openTime"] / MILLISECONDS_IN_SECOND),
            close_time=utc_timestamp(ticker["closeTime"] / MILLISECONDS_IN_SECOND),
            count=ticker["count"],
        )

    @handle_api_errors
    async def get_all_tickers(self) -> list[TickerSchema]:
        """
        Get price tickers for all symbols.

        Returns:
            List of price tickers
        """
        tickers = await self.client.get_all_tickers()

        # Convert the response to our schema
        return [
            TickerSchema(
                symbol=ticker["symbol"],
                last_price=Decimal(ticker["price"]),
                # Other fields are not available in this endpoint
                price_change=Decimal(0),
                price_change_percent=Decimal(0),
            )
            for ticker in tickers
        ]

    @handle_api_errors
    async def get_avg_price(self, symbol: str) -> dict[str, Any]:
        """
        Get current average price for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Average price information
        """
        return cast("dict[str, Any]", await self.client.get_avg_price(symbol=symbol))

    @handle_api_errors
    async def get_account_info(self) -> dict[str, Any]:
        """
        Get futures account information (requires API key).

        Returns:
            Futures account information with totalWalletBalance,
            availableBalance, totalUnrealizedProfit, positions, etc.
        """
        return cast("dict[str, Any]", await self.client.futures_account())

    @handle_api_errors
    async def get_asset_balance(self, asset: str) -> dict[str, Any]:
        """
        Get futures account balance for a specific asset (requires API key).

        Args:
            asset: Asset symbol (e.g., "USDT")

        Returns:
            Asset balance information
        """
        balances = await self.client.futures_account_balance()
        for balance in balances:
            if balance["asset"] == asset:
                return cast("dict[str, Any]", balance)
        raise ExchangeError(f"Asset not found: {asset}")

    @handle_api_errors
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        time_in_force: TimeInForce | None = None,
        client_order_id: str | None = None,
        stop_price: Decimal | None = None,
        reduce_only: bool = False,
    ) -> OrderResponseSchema:
        """
        Create a new futures order (requires API key).

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side (BUY or SELL)
            order_type: Order type (LIMIT, MARKET, STOP_MARKET, etc.)
            quantity: Order quantity
            price: Order price (required for limit orders)
            time_in_force: Time in force (required for limit orders)
            client_order_id: Client-side order ID
            stop_price: Stop price (required for STOP_MARKET/TAKE_PROFIT_MARKET)
            reduce_only: Whether this order only reduces position

        Returns:
            Order response
        """
        if order_type == OrderType.LIMIT and (price is None or time_in_force is None):
            raise ValueError(
                "Price and time_in_force are required for LIMIT orders",
            )

        if (
            order_type
            in (
                OrderType.STOP,
                OrderType.STOP_MARKET,
                OrderType.TAKE_PROFIT,
                OrderType.TAKE_PROFIT_MARKET,
            )
            and stop_price is None
        ):
            raise ValueError("Stop price is required for stop/take-profit orders")

        if quantity is None and order_type != OrderType.MARKET:
            raise ValueError("Quantity is required")

        params: dict[str, str] = {
            "symbol": symbol,
            "side": side.value,
            "type": order_type.value,
        }

        if quantity is not None:
            params["quantity"] = str(quantity)

        if price is not None:
            params["price"] = str(price)

        if time_in_force is not None:
            params["timeInForce"] = time_in_force.value

        if client_order_id is not None:
            params["newClientOrderId"] = client_order_id

        if stop_price is not None:
            params["stopPrice"] = str(stop_price)

        if reduce_only:
            params["reduceOnly"] = "true"

        response = cast(
            "dict[str, Any]",
            await self.client.futures_create_order(**params),
        )

        return self._parse_order_response(response)

    @handle_api_errors
    async def get_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> OrderResponseSchema:
        """
        Get order details (requires API key).

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            order_id: Order ID
            client_order_id: Client-side order ID

        Returns:
            Order details
        """
        if order_id is None and client_order_id is None:
            raise ValueError("Either order_id or client_order_id must be provided")

        params: dict[str, Any] = {"symbol": symbol}

        if order_id is not None:
            params["orderId"] = order_id

        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id

        response = cast(
            "dict[str, Any]",
            await self.client.futures_get_order(**params),
        )

        return self._parse_order_response(response)

    @handle_api_errors
    async def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> OrderResponseSchema:
        """
        Cancel an order (requires API key).

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            order_id: Order ID
            client_order_id: Client-side order ID

        Returns:
            Cancelled order details
        """
        if order_id is None and client_order_id is None:
            raise ValueError("Either order_id or client_order_id must be provided")

        params: dict[str, str | int] = {"symbol": symbol}

        if order_id is not None:
            params["orderId"] = order_id

        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id

        response = cast(
            "dict[str, Any]",
            await self.client.futures_cancel_order(**params),
        )

        return self._parse_order_response(response)

    @handle_api_errors
    async def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> list[OrderResponseSchema]:
        """
        Get all open orders (requires API key).

        Args:
            symbol: Trading pair symbol (optional)

        Returns:
            List of open orders
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol

        response = await self.client.futures_get_open_orders(**params)

        return [self._parse_order_response(order) for order in response]

    def _parse_order_response(self, response: dict[str, Any]) -> OrderResponseSchema:
        """
        Parse an order response from Binance API and convert it to our schema.

        Args:
            response: Order response from Binance API

        Returns:
            OrderResponseSchema object
        """
        # Parse fills if present
        fills = []
        if response.get("fills"):
            fills = [
                OrderFillSchema(
                    price=Decimal(fill["price"]),
                    qty=Decimal(fill["qty"]),
                    commission=Decimal(fill["commission"]),
                    commission_asset=fill["commissionAsset"],
                    trade_id=fill.get("tradeId"),
                )
                for fill in response["fills"]
            ]

        # Parse order status
        status = OrderStatus.NEW  # Default value
        if "status" in response:
            status = OrderStatus(response["status"])

        # Parse time in force
        time_in_force = TimeInForce.GTC  # Default value
        if "timeInForce" in response:
            time_in_force = TimeInForce(response["timeInForce"])

        # Parse order type
        order_type = OrderType.LIMIT  # Default value
        if "type" in response:
            order_type = OrderType(response["type"])

        # Parse order side
        side = OrderSide.BUY  # Default value
        if "side" in response:
            side = OrderSide(response["side"])

        return OrderResponseSchema(
            symbol=response["symbol"],
            order_id=response["orderId"],
            client_order_id=response["clientOrderId"],
            transact_time=utc_timestamp(
                response.get("transactTime", 0) / MILLISECONDS_IN_SECOND,
            )
            if "transactTime" in response
            else utc_now(),
            price=Decimal(response.get("price", "0")),
            orig_qty=Decimal(response.get("origQty", "0")),
            executed_qty=Decimal(response.get("executedQty", "0")),
            status=status,
            time_in_force=time_in_force,
            type=order_type,
            side=side,
            fills=fills,
            stop_price=Decimal(response.get("stopPrice", "0"))
            if "stopPrice" in response
            else None,
            iceberg_qty=Decimal(response.get("icebergQty", "0"))
            if "icebergQty" in response
            else None,
            time=utc_timestamp(response.get("time", 0) / MILLISECONDS_IN_SECOND)
            if "time" in response
            else None,
            update_time=utc_timestamp(
                response.get("updateTime", 0) / MILLISECONDS_IN_SECOND,
            )
            if "updateTime" in response
            else None,
            is_working=response.get("isWorking", True),
            orig_quote_order_qty=Decimal(response.get("origQuoteOrderQty", "0"))
            if "origQuoteOrderQty" in response
            else None,
            reduce_only=response.get("reduceOnly", False),
            position_side=response.get("positionSide"),
            close_position=response.get("closePosition", False),
        )

    @handle_api_errors
    async def futures_change_leverage(
        self,
        symbol: str,
        leverage: int,
    ) -> dict[str, Any]:
        """
        Change leverage for a futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            leverage: Leverage value (1-125)

        Returns:
            Response with leverage and maxNotionalValue
        """
        return cast(
            "dict[str, Any]",
            await self.client.futures_change_leverage(
                symbol=symbol,
                leverage=leverage,
            ),
        )

    async def futures_change_margin_type(
        self,
        symbol: str,
        margin_type: str,
    ) -> dict[str, Any] | None:
        """
        Change margin type for a futures symbol.

        Catches and ignores error -4046 (margin type already set).

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            margin_type: "ISOLATED" or "CROSSED"

        Returns:
            Response dict or None if already set
        """
        try:
            return cast(
                "dict[str, Any]",
                await self.client.futures_change_margin_type(
                    symbol=symbol,
                    marginType=margin_type,
                ),
            )
        except BinanceAPIException as e:
            if e.code == ERROR_CODE_MARGIN_TYPE_ALREADY_SET:
                logger.debug(
                    "Margin type already %s for %s, ignoring",
                    margin_type,
                    symbol,
                )
                return None
            raise

    @handle_api_errors
    async def futures_get_position_info(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get futures position information.

        Args:
            symbol: Trading pair symbol (optional, returns all if None)

        Returns:
            List of position info dicts with markPrice, liquidationPrice, etc.
        """
        params: dict[str, str] = {}
        if symbol is not None:
            params["symbol"] = symbol

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_position_information(**params),
        )

    @handle_api_errors
    async def futures_get_leverage_brackets(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get leverage bracket information for maintenance margin rates.

        Args:
            symbol: Trading pair symbol (optional)

        Returns:
            List of leverage bracket data
        """
        params: dict[str, str] = {}
        if symbol is not None:
            params["symbol"] = symbol

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_leverage_bracket(**params),
        )

    @handle_api_errors
    async def get_funding_rate(
        self,
        symbol: str,
        limit: int = 100,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get funding rate history for a Futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Number of records to return (default 100, max 1000)
            start_time: Start time in milliseconds or datetime
            end_time: End time in milliseconds or datetime

        Returns:
            List of funding rate records
        """
        params: dict[str, Any] = {"symbol": symbol, "limit": limit}

        if start_time is not None:
            if isinstance(start_time, datetime):
                params["startTime"] = int(
                    start_time.timestamp() * MILLISECONDS_IN_SECOND,
                )
            else:
                params["startTime"] = start_time

        if end_time is not None:
            if isinstance(end_time, datetime):
                params["endTime"] = int(end_time.timestamp() * MILLISECONDS_IN_SECOND)
            else:
                params["endTime"] = end_time

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_funding_rate(**params),
        )

    @handle_api_errors
    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        """
        Get current open interest for a Futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")

        Returns:
            Open interest data with symbol, openInterest, and time
        """
        return cast(
            "dict[str, Any]",
            await self.client.futures_open_interest(symbol=symbol),
        )

    @handle_api_errors
    async def get_open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get historical open interest for a Futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            period: Period interval (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)
            limit: Number of records to return (default 30, max 500)
            start_time: Start time in milliseconds or datetime
            end_time: End time in milliseconds or datetime

        Returns:
            List of historical open interest records
        """
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}

        if start_time is not None:
            if isinstance(start_time, datetime):
                params["startTime"] = int(
                    start_time.timestamp() * MILLISECONDS_IN_SECOND,
                )
            else:
                params["startTime"] = start_time

        if end_time is not None:
            if isinstance(end_time, datetime):
                params["endTime"] = int(end_time.timestamp() * MILLISECONDS_IN_SECOND)
            else:
                params["endTime"] = end_time

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_open_interest_hist(**params),
        )

    @handle_api_errors
    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get global long/short account ratio for a Futures symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            period: Period interval (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)
            limit: Number of records to return (default 30, max 500)
            start_time: Start time in milliseconds or datetime
            end_time: End time in milliseconds or datetime

        Returns:
            List of long/short ratio records
        """
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}

        if start_time is not None:
            if isinstance(start_time, datetime):
                params["startTime"] = int(
                    start_time.timestamp() * MILLISECONDS_IN_SECOND,
                )
            else:
                params["startTime"] = start_time

        if end_time is not None:
            if isinstance(end_time, datetime):
                params["endTime"] = int(end_time.timestamp() * MILLISECONDS_IN_SECOND)
            else:
                params["endTime"] = end_time

        return cast(
            "list[dict[str, Any]]",
            await self.client.futures_global_longshort_ratio(**params),
        )
