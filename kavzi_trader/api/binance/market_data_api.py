import time
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from kavzi_trader.api.binance.client_base import (
    BinanceClientBase,
    handle_api_errors,
)
from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.api.common.models import (
    OrderBookEntrySchema,
    OrderBookSchema,
    SymbolInfoSchema,
    TickerSchema,
)
from kavzi_trader.commons.time_utility import MILLISECONDS_IN_SECOND, utc_timestamp
from kavzi_trader.domain.candlestick import CandlestickSchema


class MarketDataApi(BinanceClientBase):
    """Exchange metadata, order book, klines and tickers."""

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

        params = self._time_params(start_time, end_time)

        # Execute request
        klines = await self.client.futures_klines(
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
        # Futures 24h ticker has no prevClosePrice or bid/ask fields
        ticker = await self.client.futures_ticker(symbol=symbol)

        # Convert the response to our schema
        return TickerSchema(
            symbol=ticker["symbol"],
            last_price=Decimal(ticker["lastPrice"]),
            price_change=Decimal(ticker["priceChange"]),
            price_change_percent=Decimal(ticker["priceChangePercent"]),
            weighted_avg_price=Decimal(ticker["weightedAvgPrice"]),
            last_qty=Decimal(ticker["lastQty"]),
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
