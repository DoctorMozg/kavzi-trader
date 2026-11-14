from datetime import datetime
from decimal import Decimal

from kavzi_trader.api.binance.client_base import (
    BinanceClientBase,
    handle_api_errors,
)
from kavzi_trader.api.common.models import TradeSchema
from kavzi_trader.commons.time_utility import MILLISECONDS_IN_SECOND, utc_timestamp


class TradesApi(BinanceClientBase):
    """Recent, historical and aggregate trade endpoints."""

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
        params: dict[str, int] = self._time_params(start_time)
        if from_id is not None:
            params["fromId"] = from_id

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
        params: dict[str, int] = self._time_params(start_time, end_time)
        if from_id is not None:
            params["fromId"] = from_id

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
