import logging
from decimal import Decimal
from typing import Any, cast

from binance.exceptions import BinanceAPIException

from kavzi_trader.api.binance.client_base import (
    BinanceClientBase,
    handle_api_errors,
)
from kavzi_trader.api.binance.constants import ERROR_CODE_MARGIN_TYPE_ALREADY_SET
from kavzi_trader.commons.time_utility import (
    MILLISECONDS_IN_SECOND,
    utc_now,
    utc_timestamp,
)
from kavzi_trader.domain.order_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.domain.order_response import OrderFillSchema, OrderResponseSchema

logger = logging.getLogger(__name__)


class OrdersApi(BinanceClientBase):
    """Futures order lifecycle plus leverage and margin-type settings."""

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
            avg_price=Decimal(response["avgPrice"]) if "avgPrice" in response else None,
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
