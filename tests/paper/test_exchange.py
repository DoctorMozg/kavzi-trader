from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.api.common.models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TickerSchema,
    TimeInForce,
)
from kavzi_trader.paper.exchange import PaperExchangeClient


@pytest.fixture()
def paper_client() -> PaperExchangeClient:
    with patch("kavzi_trader.api.binance.client.BinanceAPIClient"):
        client = PaperExchangeClient(
            initial_balance_usdt=Decimal("10000"),
            commission_rate=Decimal("0.001"),
        )
        mock_ticker = TickerSchema(
            symbol="BTCUSDT",
            last_price=Decimal("50000"),
        )
        client.get_ticker = AsyncMock(return_value=mock_ticker)
        return client


@pytest.mark.asyncio()
async def test_buy_deducts_balance(paper_client: PaperExchangeClient) -> None:
    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
    )

    assert result.status == OrderStatus.FILLED
    assert result.executed_qty == Decimal("0.1")
    assert result.symbol == "BTCUSDT"
    assert result.side == OrderSide.BUY
    assert len(result.fills) == 1

    expected = Decimal("10000") - Decimal("0.1") * Decimal("50000") * Decimal("1.001")
    assert paper_client.balance_usdt == expected


@pytest.mark.asyncio()
async def test_sell_without_holdings_rejected(
    paper_client: PaperExchangeClient,
) -> None:
    with pytest.raises(ExchangeError, match="Insufficient asset balance"):
        await paper_client.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            time_in_force=TimeInForce.GTC,
        )


@pytest.mark.asyncio()
async def test_buy_then_sell_with_profit(
    paper_client: PaperExchangeClient,
) -> None:
    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
    )
    after_buy = paper_client.balance_usdt

    exit_ticker = TickerSchema(symbol="BTCUSDT", last_price=Decimal("51000"))
    paper_client.get_ticker = AsyncMock(return_value=exit_ticker)

    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("51000"),
        time_in_force=TimeInForce.GTC,
    )
    after_sell = paper_client.balance_usdt

    assert after_buy < Decimal("10000")
    assert after_sell > after_buy
    expected_sell_proceeds = Decimal("0.1") * Decimal("51000") * Decimal("0.999")
    assert after_sell == after_buy + expected_sell_proceeds


@pytest.mark.asyncio()
async def test_insufficient_balance_rejects(
    paper_client: PaperExchangeClient,
) -> None:
    with pytest.raises(ExchangeError, match="Insufficient paper balance"):
        await paper_client.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            price=Decimal("50000"),
            time_in_force=TimeInForce.GTC,
        )


@pytest.mark.asyncio()
async def test_sell_more_than_held_rejected(
    paper_client: PaperExchangeClient,
) -> None:
    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
    )

    with pytest.raises(ExchangeError, match="Insufficient asset balance"):
        await paper_client.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            time_in_force=TimeInForce.GTC,
        )


@pytest.mark.asyncio()
async def test_protective_order_stored_as_new(
    paper_client: PaperExchangeClient,
) -> None:
    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.STOP_LOSS_LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("49000"),
        stop_price=Decimal("49500"),
        time_in_force=TimeInForce.GTC,
    )

    assert result.status == OrderStatus.NEW
    assert result.executed_qty == Decimal("0")
    assert paper_client.balance_usdt == Decimal("10000")


@pytest.mark.asyncio()
async def test_cancel_order(paper_client: PaperExchangeClient) -> None:
    order = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.STOP_LOSS_LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("49000"),
        stop_price=Decimal("49500"),
    )

    cancelled = await paper_client.cancel_order(
        symbol="BTCUSDT",
        order_id=order.order_id,
    )

    assert cancelled.status == OrderStatus.CANCELED
    assert cancelled.order_id == order.order_id


@pytest.mark.asyncio()
async def test_get_order(paper_client: PaperExchangeClient) -> None:
    order = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
    )

    retrieved = await paper_client.get_order(
        symbol="BTCUSDT",
        order_id=order.order_id,
    )

    assert retrieved.order_id == order.order_id
    assert retrieved.status == OrderStatus.FILLED


@pytest.mark.asyncio()
async def test_get_order_not_found(paper_client: PaperExchangeClient) -> None:
    with pytest.raises(ExchangeError, match="Paper order not found"):
        await paper_client.get_order(symbol="BTCUSDT", order_id=999999)


@pytest.mark.asyncio()
async def test_get_open_orders(paper_client: PaperExchangeClient) -> None:
    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
    )
    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.STOP_LOSS_LIMIT,
        quantity=Decimal("0.01"),
        stop_price=Decimal("49000"),
        price=Decimal("48900"),
    )

    open_orders = await paper_client.get_open_orders(symbol="BTCUSDT")
    assert len(open_orders) == 1
    assert open_orders[0].type == OrderType.STOP_LOSS_LIMIT


@pytest.mark.asyncio()
async def test_order_ids_are_unique(paper_client: PaperExchangeClient) -> None:
    ids: set[int] = set()
    for _ in range(5):
        order = await paper_client.create_order(
            symbol="ETHUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_LOSS_LIMIT,
            quantity=Decimal("1"),
            stop_price=Decimal("3000"),
            price=Decimal("2990"),
        )
        ids.add(order.order_id)

    assert len(ids) == 5


@pytest.mark.asyncio()
async def test_commission_calculation(
    paper_client: PaperExchangeClient,
) -> None:
    order = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("10000"),
        time_in_force=TimeInForce.GTC,
    )

    fill = order.fills[0]
    expected_commission = Decimal("0.1") * Decimal("50000") * Decimal("0.001")
    assert fill.commission == expected_commission
    assert fill.commission_asset == "USDT"


@pytest.mark.asyncio()
async def test_market_order_uses_ticker_price(
    paper_client: PaperExchangeClient,
) -> None:
    mock_ticker = TickerSchema(
        symbol="BTCUSDT",
        last_price=Decimal("55000"),
    )
    paper_client.get_ticker = AsyncMock(return_value=mock_ticker)

    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
    )

    assert result.status == OrderStatus.FILLED
    assert result.price == Decimal("55000")
    paper_client.get_ticker.assert_awaited_once_with("BTCUSDT")


@pytest.mark.asyncio()
async def test_get_account_info(paper_client: PaperExchangeClient) -> None:
    info = await paper_client.get_account_info()
    balances = info["balances"]
    assert len(balances) == 1
    assert balances[0]["asset"] == "USDT"
    assert balances[0]["free"] == "10000"


@pytest.mark.asyncio()
async def test_get_asset_balance_usdt(
    paper_client: PaperExchangeClient,
) -> None:
    balance = await paper_client.get_asset_balance("USDT")
    assert balance["asset"] == "USDT"
    assert balance["free"] == "10000"


@pytest.mark.asyncio()
async def test_get_asset_balance_other(
    paper_client: PaperExchangeClient,
) -> None:
    balance = await paper_client.get_asset_balance("BTC")
    assert balance["asset"] == "BTC"
    assert balance["free"] == "0"


@pytest.mark.asyncio()
async def test_take_profit_order_stored_as_new(
    paper_client: PaperExchangeClient,
) -> None:
    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.TAKE_PROFIT_LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("55000"),
        stop_price=Decimal("55000"),
        time_in_force=TimeInForce.GTC,
    )

    assert result.status == OrderStatus.NEW
    assert paper_client.balance_usdt == Decimal("10000")
