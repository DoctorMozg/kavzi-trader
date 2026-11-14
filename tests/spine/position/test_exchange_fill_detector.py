import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.order_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.domain.state_schemas import OpenOrderSchema
from kavzi_trader.spine.position.exchange_fill_detector import ExchangeFillDetector


def _linked_order(order_id: str, order_type: OrderType) -> OpenOrderSchema:
    return OpenOrderSchema(
        order_id=order_id,
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=order_type,
        price=Decimal(0),
        quantity=Decimal(1),
        status=OrderStatus.NEW,
        linked_position_id="pos-1",
        created_at=utc_now(),
    )


def _exchange_order(
    order_id: int,
    status: OrderStatus,
    avg_price: Decimal | None = None,
) -> OrderResponseSchema:
    now = utc_now()
    return OrderResponseSchema(
        symbol="BTCUSDT",
        order_id=order_id,
        client_order_id=f"c-{order_id}",
        transact_time=now,
        price=Decimal(0),
        orig_qty=Decimal(1),
        executed_qty=Decimal(1) if status == OrderStatus.FILLED else Decimal(0),
        status=status,
        time_in_force=TimeInForce.GTC,
        type=OrderType.STOP_MARKET,
        side=OrderSide.SELL,
        avg_price=avg_price,
    )


@pytest.fixture
def exchange() -> AsyncMock:
    mock = AsyncMock()
    mock.futures_get_position_info = AsyncMock(
        return_value=[{"symbol": "BTCUSDT", "positionAmt": "1"}],
    )
    return mock


@pytest.fixture
def state() -> AsyncMock:
    mock = AsyncMock()
    mock.orders = AsyncMock()
    mock.orders.get_by_position = AsyncMock(
        return_value=[
            _linked_order("11", OrderType.STOP_MARKET),
            _linked_order("12", OrderType.TAKE_PROFIT_MARKET),
        ],
    )
    return mock


def _orders_by_id(
    exchange: AsyncMock,
    orders: dict[int, OrderResponseSchema | ExchangeError],
) -> None:
    async def _get_order(
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> OrderResponseSchema:
        result = orders[order_id]  # type: ignore[index]
        if isinstance(result, ExchangeError):
            raise result
        return result

    exchange.get_order = AsyncMock(side_effect=_get_order)


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
async def test_filled_stop_loss_is_detected_with_real_fill_price(
    exchange: AsyncMock,
    state: AsyncMock,
    position_factory,
    side: str,
) -> None:
    _orders_by_id(
        exchange,
        {
            11: _exchange_order(11, OrderStatus.FILLED, Decimal("89.5")),
            12: _exchange_order(12, OrderStatus.NEW),
        },
    )
    detector = ExchangeFillDetector(exchange, state)

    async with asyncio.timeout(2):
        result = await detector.detect(position_factory(side=side))

    assert result is not None
    assert result.close_reason == "stop_loss_filled"
    assert result.exit_price == Decimal("89.5")


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
async def test_filled_take_profit_is_detected(
    exchange: AsyncMock,
    state: AsyncMock,
    position_factory,
    side: str,
) -> None:
    _orders_by_id(
        exchange,
        {
            11: _exchange_order(11, OrderStatus.NEW),
            12: _exchange_order(12, OrderStatus.FILLED, Decimal("120.5")),
        },
    )
    detector = ExchangeFillDetector(exchange, state)

    result = await detector.detect(position_factory(side=side))

    assert result is not None
    assert result.close_reason == "take_profit_filled"
    assert result.exit_price == Decimal("120.5")


async def test_live_position_with_resting_orders_is_left_alone(
    exchange: AsyncMock,
    state: AsyncMock,
    position_factory,
) -> None:
    _orders_by_id(
        exchange,
        {
            11: _exchange_order(11, OrderStatus.NEW),
            12: _exchange_order(12, OrderStatus.NEW),
        },
    )
    detector = ExchangeFillDetector(exchange, state)

    assert await detector.detect(position_factory()) is None


async def test_position_gone_on_exchange_is_detected_without_exit_price(
    exchange: AsyncMock,
    state: AsyncMock,
    position_factory,
) -> None:
    _orders_by_id(
        exchange,
        {
            11: _exchange_order(11, OrderStatus.CANCELED),
            12: _exchange_order(12, OrderStatus.CANCELED),
        },
    )
    exchange.futures_get_position_info = AsyncMock(
        return_value=[{"symbol": "BTCUSDT", "positionAmt": "0.000"}],
    )
    detector = ExchangeFillDetector(exchange, state)

    result = await detector.detect(position_factory())

    assert result is not None
    assert result.close_reason == "exchange_position_closed"
    assert result.exit_price is None


async def test_unknown_order_falls_back_to_position_check(
    exchange: AsyncMock,
    state: AsyncMock,
    position_factory,
) -> None:
    _orders_by_id(
        exchange,
        {
            11: ExchangeError("Order does not exist", code=-2013),
            12: ExchangeError("Order does not exist", code=-2013),
        },
    )
    exchange.futures_get_position_info = AsyncMock(return_value=[])
    detector = ExchangeFillDetector(exchange, state)

    result = await detector.detect(position_factory())

    assert result is not None
    assert result.close_reason == "exchange_position_closed"
