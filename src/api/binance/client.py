"""
Binance REST API client implementation.

This module provides a client for interacting with the Binance API, wrapping the
python-binance library to fit our project's interfaces and data models.
"""

import hashlib
import hmac
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, Dict, List, Union, cast

from binance.client import Client as BinanceAPIClient
from binance.exceptions import BinanceAPIException, BinanceRequestException

from src.api.binance.constants import (
    BINANCE_API_TESTNET_URL,
    BINANCE_API_URL,
    ENDPOINTS,
    KLINE_INTERVALS,
)
from src.api.common.exceptions import (
    APIError,
    AuthenticationError,
    ExchangeError,
    RateLimitError,
    RequestError,
)
from src.api.common.models import (
    CandlestickSchema,
    OrderBookEntrySchema,
    OrderBookSchema,
    OrderResponseSchema,
    OrderSide,
    OrderStatus,
    OrderType,
    SymbolInfoSchema,
    TickerSchema,
    TimeInForce,
    TradeSchema,
)

logger = logging.getLogger(__name__)


class BinanceClient:
    """
    Client for interacting with the Binance API.
    
    This class wraps the python-binance library to provide a consistent
    interface with the rest of our application, handling serialization,
    error mapping, and data conversion.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = False,
        timeout: int = 30,
        proxies: Optional[Dict[str, str]] = None,
        show_limit_usage: bool = False,
    ):
        """
        Initialize the Binance client.
        
        Args:
            api_key: API key for authenticated endpoints
            api_secret: API secret for authenticated endpoints
            testnet: Whether to use the testnet
            timeout: Request timeout in seconds
            proxies: Proxy configuration for requests
            show_limit_usage: Whether to log rate limit usage
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.timeout = timeout
        self.show_limit_usage = show_limit_usage
        self.base_url = BINANCE_API_TESTNET_URL if testnet else BINANCE_API_URL
        
        # Initialize the python-binance client
        self.client = BinanceAPIClient(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            timeout=timeout,
            requests_params={"proxies": proxies} if proxies else None,
        )
        
        logger.info(
            "Initialized Binance client with %s",
            f"testnet={testnet}, timeout={timeout}",
        )
    
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
            if error_code in (-2015, -2014):
                raise AuthenticationError(message)
            
            # Rate limit errors
            elif error_code == -1429:
                raise RateLimitError(message)
            
            # Exchange-specific errors
            else:
                raise ExchangeError(message, code=error_code)
        
        elif isinstance(error, BinanceRequestException):
            raise RequestError(message)
        
        else:
            raise APIError(f"Unexpected error: {message}")
    
    def _get_timestamp(self) -> int:
        """
        Get current timestamp in milliseconds.
        
        Returns:
            Current timestamp in milliseconds
        """
        return int(time.time() * 1000)

    def ping(self) -> Dict[str, bool]:
        """
        Test connectivity to the API.
        
        Returns:
            Dictionary with {'success': True} on success
        """
        try:
            self.client.ping()
            return {"success": True}
        except Exception as e:
            self._handle_error(e)
            return {"success": False}  # This won't be reached, but keeps type checker happy

    def get_server_time(self) -> Dict[str, int]:
        """
        Get the server time.
        
        Returns:
            Dictionary with {'serverTime': timestamp} in milliseconds
        """
        try:
            result = self.client.get_server_time()
            return result
        except Exception as e:
            self._handle_error(e)
            raise  # To satisfy type checker

    def get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange information including rate limits, symbol information.
        
        Returns:
            Exchange information
        """
        try:
            return self.client.get_exchange_info()
        except Exception as e:
            self._handle_error(e)
            raise  # To satisfy type checker

    def get_symbol_info(self, symbol: str) -> SymbolInfoSchema:
        """
        Get detailed information for a specific symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            
        Returns:
            Symbol information
        """
        try:
            # Get all symbols and find the one we want
            exchange_info = self.client.get_exchange_info()
            symbol_info = None
            
            for info in exchange_info["symbols"]:
                if info["symbol"] == symbol:
                    symbol_info = info
                    break
            
            if not symbol_info:
                raise ExchangeError(f"Symbol not found: {symbol}")
            
            # Extract relevant information and convert to our schema
            filters = {filter["filterType"]: filter for filter in symbol_info["filters"]}
            
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
            min_notional = Decimal(filters.get("MIN_NOTIONAL", {}).get("minNotional", "0"))
            
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
            
        except Exception as e:
            if not isinstance(e, ExchangeError):
                self._handle_error(e)
            raise

    def get_orderbook(self, symbol: str, limit: int = 100) -> OrderBookSchema:
        """
        Get order book for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Number of entries to return (default 100, max 5000)
            
        Returns:
            Order book with bids and asks
        """
        try:
            depth = self.client.get_order_book(symbol=symbol, limit=limit)
            
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
                timestamp=datetime.fromtimestamp(int(time.time())),
            )
            
        except Exception as e:
            self._handle_error(e)
            raise

    def get_recent_trades(self, symbol: str, limit: int = 500) -> List[TradeSchema]:
        """
        Get recent trades for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Number of trades to return (default 500, max 1000)
            
        Returns:
            List of recent trades
        """
        try:
            trades = self.client.get_recent_trades(symbol=symbol, limit=limit)
            
            # Convert the response to our schema
            trade_schemas = []
            for trade in trades:
                trade_schemas.append(
                    TradeSchema(
                        id=trade["id"],
                        price=Decimal(trade["price"]),
                        qty=Decimal(trade["qty"]),
                        time=datetime.fromtimestamp(trade["time"] / 1000),
                        is_buyer_maker=trade["isBuyerMaker"],
                        is_best_match=trade.get("isBestMatch", True),
                        quote_qty=Decimal(trade.get("quoteQty", "0")),
                    )
                )
                
            return trade_schemas
            
        except Exception as e:
            self._handle_error(e)
            raise

    def get_historical_trades(
        self, 
        symbol: str, 
        limit: int = 500, 
        from_id: Optional[int] = None,
        start_time: Optional[Union[int, datetime]] = None,
    ) -> List[TradeSchema]:
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
        try:
            # Process start_time if it's a datetime
            start_time_ms = None
            if start_time is not None:
                if isinstance(start_time, datetime):
                    start_time_ms = int(start_time.timestamp() * 1000)
                else:
                    start_time_ms = start_time
            
            # Prepare parameters
            params = {}
            if from_id is not None:
                params["fromId"] = from_id
            if start_time_ms is not None:
                params["startTime"] = start_time_ms
            
            # Execute request
            trades = self.client.get_historical_trades(
                symbol=symbol, 
                limit=limit, 
                **params
            )
            
            # Convert the response to our schema
            trade_schemas = []
            for trade in trades:
                trade_schemas.append(
                    TradeSchema(
                        id=trade["id"],
                        price=Decimal(trade["price"]),
                        qty=Decimal(trade["qty"]),
                        time=datetime.fromtimestamp(trade["time"] / 1000),
                        is_buyer_maker=trade["isBuyerMaker"],
                        is_best_match=trade.get("isBestMatch", True),
                        quote_qty=Decimal(trade.get("quoteQty", "0")),
                    )
                )
                
            return trade_schemas
            
        except Exception as e:
            self._handle_error(e)
            raise

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[Union[int, datetime]] = None,
        end_time: Optional[Union[int, datetime]] = None,
        limit: int = 500,
    ) -> List[CandlestickSchema]:
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
        try:
            # Validate interval
            if interval not in KLINE_INTERVALS:
                valid_intervals = ", ".join(KLINE_INTERVALS.keys())
                raise ValueError(
                    f"Invalid interval: {interval}. Valid intervals: {valid_intervals}"
                )
            
            # Process start_time and end_time if they're datetime objects
            start_time_ms = None
            if start_time is not None:
                if isinstance(start_time, datetime):
                    start_time_ms = int(start_time.timestamp() * 1000)
                else:
                    start_time_ms = start_time
                    
            end_time_ms = None
            if end_time is not None:
                if isinstance(end_time, datetime):
                    end_time_ms = int(end_time.timestamp() * 1000)
                else:
                    end_time_ms = end_time
            
            # Prepare parameters
            params = {}
            if start_time_ms is not None:
                params["startTime"] = start_time_ms
            if end_time_ms is not None:
                params["endTime"] = end_time_ms
            
            # Execute request
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit,
                **params
            )
            
            # Convert the response to our schema
            kline_schemas = []
            for kline in klines:
                kline_schemas.append(
                    CandlestickSchema(
                        open_time=datetime.fromtimestamp(kline[0] / 1000),
                        open_price=Decimal(kline[1]),
                        high_price=Decimal(kline[2]),
                        low_price=Decimal(kline[3]),
                        close_price=Decimal(kline[4]),
                        volume=Decimal(kline[5]),
                        close_time=datetime.fromtimestamp(kline[6] / 1000),
                        quote_volume=Decimal(kline[7]),
                        trades_count=kline[8],
                        taker_buy_base_volume=Decimal(kline[9]),
                        taker_buy_quote_volume=Decimal(kline[10]),
                        interval=interval,
                        symbol=symbol,
                    )
                )
                
            return kline_schemas
            
        except Exception as e:
            if not isinstance(e, ValueError):
                self._handle_error(e)
            raise

    def get_ticker(self, symbol: str) -> TickerSchema:
        """
        Get 24hr ticker price change statistics for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            
        Returns:
            Ticker statistics
        """
        try:
            ticker = self.client.get_ticker(symbol=symbol)
            
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
                open_time=datetime.fromtimestamp(ticker["openTime"] / 1000),
                close_time=datetime.fromtimestamp(ticker["closeTime"] / 1000),
                count=ticker["count"],
            )
            
        except Exception as e:
            self._handle_error(e)
            raise

    def get_all_tickers(self) -> List[TickerSchema]:
        """
        Get price tickers for all symbols.
        
        Returns:
            List of price tickers
        """
        try:
            tickers = self.client.get_all_tickers()
            
            # Convert the response to our schema
            ticker_schemas = []
            for ticker in tickers:
                ticker_schemas.append(
                    TickerSchema(
                        symbol=ticker["symbol"],
                        last_price=Decimal(ticker["price"]),
                        # Other fields are not available in this endpoint
                        price_change=Decimal(0),
                        price_change_percent=Decimal(0),
                    )
                )
                
            return ticker_schemas
            
        except Exception as e:
            self._handle_error(e)
            raise

    def get_avg_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get current average price for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            
        Returns:
            Average price information
        """
        try:
            return self.client.get_avg_price(symbol=symbol)
        except Exception as e:
            self._handle_error(e)
            raise

    def get_account_info(self) -> Dict[str, Any]:
        """
        Get account information (requires API key).
        
        Returns:
            Account information
        """
        try:
            return self.client.get_account()
        except Exception as e:
            self._handle_error(e)
            raise

    def get_asset_balance(self, asset: str) -> Dict[str, Any]:
        """
        Get asset balance for a specific asset (requires API key).
        
        Args:
            asset: Asset symbol (e.g., "BTC")
            
        Returns:
            Asset balance information
        """
        try:
            return self.client.get_asset_balance(asset=asset)
        except Exception as e:
            self._handle_error(e)
            raise

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_order_id: Optional[str] = None,
        stop_price: Optional[Decimal] = None,
        iceberg_qty: Optional[Decimal] = None,
        test: bool = False,
    ) -> OrderResponseSchema:
        """
        Create a new order (requires API key).
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side (BUY or SELL)
            order_type: Order type (LIMIT, MARKET, etc.)
            quantity: Order quantity
            price: Order price (required for limit orders)
            time_in_force: Time in force (required for limit orders)
            client_order_id: Client-side order ID
            stop_price: Stop price (required for stop orders)
            iceberg_qty: Iceberg quantity
            test: Whether to create a test order (no execution)
            
        Returns:
            Order response
        """
        try:
            # Validate required parameters
            if order_type == OrderType.LIMIT and (price is None or time_in_force is None):
                raise ValueError("Price and time_in_force are required for LIMIT orders")
                
            if order_type in (OrderType.STOP_LOSS_LIMIT, OrderType.TAKE_PROFIT_LIMIT) and stop_price is None:
                raise ValueError("Stop price is required for stop orders")
                
            if quantity is None and order_type != OrderType.MARKET:
                raise ValueError("Quantity is required")
            
            # Prepare parameters
            params = {
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
                
            if iceberg_qty is not None:
                params["icebergQty"] = str(iceberg_qty)
            
            # Execute request
            if test:
                # Test order doesn't return full response, just success
                self.client.create_test_order(**params)
                # Return a minimal response for test orders
                return OrderResponseSchema(
                    symbol=symbol,
                    order_id=0,
                    client_order_id=client_order_id or "",
                    transact_time=datetime.now(),
                    price=price or Decimal(0),
                    orig_qty=quantity or Decimal(0),
                    executed_qty=Decimal(0),
                    status=OrderStatus.NEW,
                    time_in_force=time_in_force or TimeInForce.GTC,
                    type=order_type,
                    side=side,
                )
            else:
                response = self.client.create_order(**params)
                
                # Convert the response to our schema
                return self._parse_order_response(response)
                
        except Exception as e:
            if not isinstance(e, ValueError):
                self._handle_error(e)
            raise

    def get_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
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
        try:
            if order_id is None and client_order_id is None:
                raise ValueError("Either order_id or client_order_id must be provided")
                
            params = {"symbol": symbol}
            
            if order_id is not None:
                params["orderId"] = order_id
                
            if client_order_id is not None:
                params["origClientOrderId"] = client_order_id
                
            response = self.client.get_order(**params)
            
            # Convert the response to our schema
            return self._parse_order_response(response)
            
        except Exception as e:
            if not isinstance(e, ValueError):
                self._handle_error(e)
            raise

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
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
        try:
            if order_id is None and client_order_id is None:
                raise ValueError("Either order_id or client_order_id must be provided")
                
            params = {"symbol": symbol}
            
            if order_id is not None:
                params["orderId"] = order_id
                
            if client_order_id is not None:
                params["origClientOrderId"] = client_order_id
                
            response = self.client.cancel_order(**params)
            
            # Convert the response to our schema
            return self._parse_order_response(response)
            
        except Exception as e:
            if not isinstance(e, ValueError):
                self._handle_error(e)
            raise

    def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponseSchema]:
        """
        Get all open orders (requires API key).
        
        Args:
            symbol: Trading pair symbol (optional)
            
        Returns:
            List of open orders
        """
        try:
            params = {}
            if symbol is not None:
                params["symbol"] = symbol
                
            response = self.client.get_open_orders(**params)
            
            # Convert the response to our schema
            return [self._parse_order_response(order) for order in response]
            
        except Exception as e:
            self._handle_error(e)
            raise

    def _parse_order_response(self, response: Dict[str, Any]) -> OrderResponseSchema:
        """
        Parse an order response from Binance API and convert it to our schema.
        
        Args:
            response: Order response from Binance API
            
        Returns:
            OrderResponseSchema object
        """
        # Parse fills if present
        fills = []
        if "fills" in response and response["fills"]:
            from src.api.common.models import OrderFillSchema
            
            for fill in response["fills"]:
                fills.append(
                    OrderFillSchema(
                        price=Decimal(fill["price"]),
                        qty=Decimal(fill["qty"]),
                        commission=Decimal(fill["commission"]),
                        commission_asset=fill["commissionAsset"],
                        trade_id=fill.get("tradeId"),
                    )
                )
        
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
        
        # Create and return OrderResponseSchema
        return OrderResponseSchema(
            symbol=response["symbol"],
            order_id=response["orderId"],
            client_order_id=response["clientOrderId"],
            transact_time=datetime.fromtimestamp(response.get("transactTime", 0) / 1000) if "transactTime" in response else datetime.now(),
            price=Decimal(response.get("price", "0")),
            orig_qty=Decimal(response.get("origQty", "0")),
            executed_qty=Decimal(response.get("executedQty", "0")),
            status=status,
            time_in_force=time_in_force,
            type=order_type,
            side=side,
            fills=fills,
            stop_price=Decimal(response.get("stopPrice", "0")) if "stopPrice" in response else None,
            iceberg_qty=Decimal(response.get("icebergQty", "0")) if "icebergQty" in response else None,
            time=datetime.fromtimestamp(response.get("time", 0) / 1000) if "time" in response else None,
            update_time=datetime.fromtimestamp(response.get("updateTime", 0) / 1000) if "updateTime" in response else None,
            is_working=response.get("isWorking", True),
            orig_quote_order_qty=Decimal(response.get("origQuoteOrderQty", "0")) if "origQuoteOrderQty" in response else None,
        ) 