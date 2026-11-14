from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.domain.order_enums import OrderSide, OrderStatus, OrderType
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.domain.state_schemas import OpenOrderSchema, PositionSchema
from kavzi_trader.spine.execution.linked_orders import LinkedOrderService


def _order() -> OpenOrderSchema:
    return OpenOrderSchema(
        order_id="42",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.STOP_MARKET,
        price=Decimal(49000),
        quantity=Decimal("0.1"),
        status=OrderStatus.NEW,
        linked_position_id="pos-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def exchange() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def state() -> AsyncMock:
    manager = AsyncMock()
    manager.orders.get_by_position = AsyncMock(return_value=[_order()])
    return manager


@pytest.fixture
def service(exchange: AsyncMock, state: AsyncMock) -> LinkedOrderService:
    return LinkedOrderService(exchange, state)


@pytest.mark.asyncio
async def test_cancel_success_removes_record(
    service: LinkedOrderService,
    exchange: AsyncMock,
    state: AsyncMock,
) -> None:
    await service.cancel(_order())

    exchange.cancel_order.assert_awaited_once_with(symbol="BTCUSDT", order_id=42)
    state.remove_order.assert_awaited_once_with("42")


@pytest.mark.asyncio
async def test_cancel_unknown_order_removes_record(
    service: LinkedOrderService,
    exchange: AsyncMock,
    state: AsyncMock,
) -> None:
    exchange.cancel_order.side_effect = ExchangeError("Unknown order", code=-2011)

    await service.cancel(_order())

    state.remove_order.assert_awaited_once_with("42")


@pytest.mark.parametrize(
    "error",
    [ExchangeError("bad", code=-1007), RuntimeError("boom")],
)
@pytest.mark.asyncio
async def test_cancel_other_failure_keeps_record(
    service: LinkedOrderService,
    exchange: AsyncMock,
    state: AsyncMock,
    error: Exception,
) -> None:
    exchange.cancel_order.side_effect = error

    await service.cancel(_order())

    state.remove_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_for_position_tolerates_unknown_order(
    service: LinkedOrderService,
    exchange: AsyncMock,
    state: AsyncMock,
) -> None:
    exchange.cancel_order.side_effect = ExchangeError("Unknown order", code=-2011)
    position = PositionSchema.model_construct(id="pos-1", symbol="BTCUSDT")

    await service.cancel_for_position(position)

    state.remove_order.assert_awaited_once_with("42")


@pytest.mark.parametrize("position_id", ["pos-1", None])
@pytest.mark.asyncio
async def test_save_links_order_to_position(
    service: LinkedOrderService,
    state: AsyncMock,
    position_id: str | None,
) -> None:
    response = OrderResponseSchema.model_construct(
        order_id=7,
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_MARKET,
        price=Decimal(1),
        orig_qty=Decimal(1),
        executed_qty=Decimal(0),
        status=OrderStatus.NEW,
        time=datetime(2026, 1, 1, tzinfo=UTC),
    )

    await service.save(response, position_id)

    saved = state.save_order.await_args.args[0]
    assert saved.order_id == "7"
    assert saved.linked_position_id == position_id
