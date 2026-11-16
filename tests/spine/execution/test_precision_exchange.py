from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.order_enums import OrderSide, OrderType
from kavzi_trader.domain.state_schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.spine.execution.precision_exchange import PrecisionExchangeClient
from kavzi_trader.spine.execution.protective_orders import ProtectiveOrderPlacer
from kavzi_trader.spine.precision.symbol_precision import (
    OrderPrecisionError,
    SymbolPrecision,
)

SYMBOL = "BTCUSDT"


@pytest.fixture
def inner() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def exchange(inner: AsyncMock, precision: SymbolPrecision) -> PrecisionExchangeClient:
    return PrecisionExchangeClient(inner, precision)


def _sent(inner: AsyncMock) -> dict[str, object]:
    return dict(inner.create_order.await_args.kwargs)


async def test_market_quantity_floors_to_step(
    exchange: PrecisionExchangeClient, inner: AsyncMock
) -> None:
    await exchange.create_order(
        SYMBOL, OrderSide.BUY, OrderType.MARKET, quantity=Decimal("1.239")
    )
    assert _sent(inner)["quantity"] == Decimal("1.23")


@pytest.mark.parametrize(
    ("order_type", "side", "raw", "expected"),
    [
        # long SL (SELL stop) rounds up, short SL (BUY stop) rounds down
        (OrderType.STOP_MARKET, OrderSide.SELL, "95.2", "95.5"),
        (OrderType.STOP_MARKET, OrderSide.BUY, "105.2", "105.0"),
        # long TP (SELL) rounds down, short TP (BUY) rounds up
        (OrderType.TAKE_PROFIT_MARKET, OrderSide.SELL, "110.7", "110.5"),
        (OrderType.TAKE_PROFIT_MARKET, OrderSide.BUY, "90.2", "90.5"),
    ],
)
async def test_protective_prices_are_tick_aligned_toward_entry(
    exchange: PrecisionExchangeClient,
    inner: AsyncMock,
    order_type: OrderType,
    side: OrderSide,
    raw: str,
    expected: str,
) -> None:
    await exchange.create_order(
        SYMBOL,
        side,
        order_type,
        quantity=Decimal(1),
        stop_price=Decimal(raw),
        reduce_only=True,
    )
    assert _sent(inner)["stop_price"] == Decimal(expected)


async def test_limit_price_never_worse_than_planned(
    exchange: PrecisionExchangeClient, inner: AsyncMock
) -> None:
    await exchange.create_order(
        SYMBOL, OrderSide.BUY, OrderType.LIMIT, Decimal(1), price=Decimal("100.4")
    )
    assert _sent(inner)["price"] == Decimal(100)
    await exchange.create_order(
        SYMBOL, OrderSide.SELL, OrderType.LIMIT, Decimal(1), price=Decimal("100.4")
    )
    assert _sent(inner)["price"] == Decimal("100.5")


async def test_sub_minimum_quantity_is_not_sent(
    exchange: PrecisionExchangeClient, inner: AsyncMock
) -> None:
    with pytest.raises(OrderPrecisionError, match="rounds to zero"):
        await exchange.create_order(
            SYMBOL, OrderSide.BUY, OrderType.MARKET, quantity=Decimal("0.004")
        )
    inner.create_order.assert_not_awaited()


async def test_limit_below_min_notional_is_not_sent(
    exchange: PrecisionExchangeClient, inner: AsyncMock
) -> None:
    with pytest.raises(OrderPrecisionError, match="notional"):
        await exchange.create_order(
            SYMBOL, OrderSide.BUY, OrderType.LIMIT, Decimal("0.5"), price=Decimal(100)
        )
    inner.create_order.assert_not_awaited()


async def test_reduce_only_close_below_min_notional_is_sent(
    exchange: PrecisionExchangeClient, inner: AsyncMock
) -> None:
    await exchange.create_order(
        SYMBOL,
        OrderSide.SELL,
        OrderType.LIMIT,
        Decimal("0.5"),
        price=Decimal(100),
        reduce_only=True,
    )
    inner.create_order.assert_awaited_once()


async def test_placer_sends_tick_aligned_sl_and_tp(
    exchange: PrecisionExchangeClient, inner: AsyncMock
) -> None:
    placer = ProtectiveOrderPlacer(
        exchange, AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    )
    now = utc_now()
    short = PositionSchema(
        id="pos-1",
        symbol=SYMBOL,
        side="SHORT",
        quantity=Decimal(1),
        entry_price=Decimal(100),
        stop_loss=Decimal("105.2"),
        take_profit=Decimal("90.2"),
        current_stop_loss=Decimal("105.2"),
        management_config=PositionManagementConfigSchema(),
        opened_at=now,
        updated_at=now,
    )

    await placer.place_stop_loss(short)
    await placer.place_take_profit(short)

    sent = [c.kwargs["stop_price"] for c in inner.create_order.await_args_list]
    # short: SL rounds down toward entry, TP rounds up toward entry
    assert sent == [Decimal("105.0"), Decimal("90.5")]
