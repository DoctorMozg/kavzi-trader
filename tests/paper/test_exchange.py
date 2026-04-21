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
from kavzi_trader.paper.exchange import PaperExchangeClient, _PaperPositionTracker


@pytest.fixture
def paper_client() -> PaperExchangeClient:
    with patch("kavzi_trader.api.binance.client.BinanceAPIClient"):
        client = PaperExchangeClient(
            initial_balance_usdt=Decimal(10000),
            commission_rate=Decimal("0.001"),
        )
        mock_ticker = TickerSchema(
            symbol="BTCUSDT",
            last_price=Decimal(50000),
        )
        client.get_ticker = AsyncMock(return_value=mock_ticker)
        return client


@pytest.mark.asyncio
async def test_buy_opens_long_deducts_margin(
    paper_client: PaperExchangeClient,
) -> None:
    """BUY opens a LONG position, deducting initial margin + commission."""
    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal(50000),
        time_in_force=TimeInForce.GTC,
    )

    assert result.status == OrderStatus.FILLED
    assert result.executed_qty == Decimal("0.1")
    assert result.symbol == "BTCUSDT"
    assert result.side == OrderSide.BUY
    assert len(result.fills) == 1

    # leverage=1 (default): margin = 0.1 * 50000 / 1 = 5000
    # commission = 0.1 * 50000 * 0.001 = 5
    expected = Decimal(10000) - Decimal(5000) - Decimal(5)
    assert paper_client.balance_usdt == expected


@pytest.mark.asyncio
async def test_sell_opens_short_deducts_margin(
    paper_client: PaperExchangeClient,
) -> None:
    """SELL without existing position opens a SHORT (futures behaviour)."""
    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal(50000),
        time_in_force=TimeInForce.GTC,
    )

    assert result.status == OrderStatus.FILLED
    # leverage=1 (default): margin = 0.1 * 50000 = 5000, commission = 5
    expected = Decimal(10000) - Decimal(5000) - Decimal(5)
    assert paper_client.balance_usdt == expected


@pytest.mark.asyncio
async def test_long_then_close_with_profit(
    paper_client: PaperExchangeClient,
) -> None:
    """Open LONG, then close (SELL) at a higher price for profit."""
    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal(50000),
        time_in_force=TimeInForce.GTC,
    )
    after_buy = paper_client.balance_usdt

    exit_ticker = TickerSchema(symbol="BTCUSDT", last_price=Decimal(51000))
    paper_client.get_ticker = AsyncMock(return_value=exit_ticker)

    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
    )
    after_sell = paper_client.balance_usdt

    assert after_sell > after_buy


@pytest.mark.asyncio
async def test_insufficient_margin_rejects(
    paper_client: PaperExchangeClient,
) -> None:
    """Opening a position without sufficient margin should be rejected."""
    with pytest.raises(ExchangeError, match="Insufficient margin"):
        await paper_client.create_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal(1),
            price=Decimal(50000),
            time_in_force=TimeInForce.GTC,
        )


@pytest.mark.asyncio
async def test_reduce_only_without_position_rejected(
    paper_client: PaperExchangeClient,
) -> None:
    """reduce_only order without a matching position is rejected."""
    with pytest.raises(ExchangeError, match="reduce_only"):
        await paper_client.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            reduce_only=True,
        )


@pytest.mark.asyncio
async def test_protective_order_stored_as_new(
    paper_client: PaperExchangeClient,
) -> None:
    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.STOP_MARKET,
        quantity=Decimal("0.1"),
        stop_price=Decimal(49500),
        reduce_only=True,
    )

    assert result.status == OrderStatus.NEW
    assert result.executed_qty == Decimal(0)
    assert paper_client.balance_usdt == Decimal(10000)


@pytest.mark.asyncio
async def test_cancel_order(paper_client: PaperExchangeClient) -> None:
    order = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.STOP_MARKET,
        quantity=Decimal("0.1"),
        stop_price=Decimal(49500),
    )

    cancelled = await paper_client.cancel_order(
        symbol="BTCUSDT",
        order_id=order.order_id,
    )

    assert cancelled.status == OrderStatus.CANCELED
    assert cancelled.order_id == order.order_id


@pytest.mark.asyncio
async def test_get_order(paper_client: PaperExchangeClient) -> None:
    order = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal(50000),
        time_in_force=TimeInForce.GTC,
    )

    retrieved = await paper_client.get_order(
        symbol="BTCUSDT",
        order_id=order.order_id,
    )

    assert retrieved.order_id == order.order_id
    assert retrieved.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_get_order_not_found(paper_client: PaperExchangeClient) -> None:
    with pytest.raises(ExchangeError, match="Paper order not found"):
        await paper_client.get_order(symbol="BTCUSDT", order_id=999999)


@pytest.mark.asyncio
async def test_get_open_orders(paper_client: PaperExchangeClient) -> None:
    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal(50000),
        time_in_force=TimeInForce.GTC,
    )
    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.STOP_MARKET,
        quantity=Decimal("0.01"),
        stop_price=Decimal(49000),
    )

    open_orders = await paper_client.get_open_orders(symbol="BTCUSDT")
    assert len(open_orders) == 1
    assert open_orders[0].type == OrderType.STOP_MARKET


@pytest.mark.asyncio
async def test_order_ids_are_unique(paper_client: PaperExchangeClient) -> None:
    ids: set[int] = set()
    for _ in range(5):
        order = await paper_client.create_order(
            symbol="ETHUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_MARKET,
            quantity=Decimal(1),
            stop_price=Decimal(3000),
        )
        ids.add(order.order_id)

    assert len(ids) == 5


@pytest.mark.asyncio
async def test_commission_calculation(
    paper_client: PaperExchangeClient,
) -> None:
    order = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal(10000),
        time_in_force=TimeInForce.GTC,
    )

    fill = order.fills[0]
    expected_commission = Decimal("0.1") * Decimal(50000) * Decimal("0.001")
    assert fill.commission == expected_commission
    assert fill.commission_asset == "USDT"


@pytest.mark.asyncio
async def test_market_order_uses_ticker_price(
    paper_client: PaperExchangeClient,
) -> None:
    mock_ticker = TickerSchema(
        symbol="BTCUSDT",
        last_price=Decimal(55000),
    )
    paper_client.get_ticker = AsyncMock(return_value=mock_ticker)

    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
    )

    assert result.status == OrderStatus.FILLED
    assert result.price == Decimal(55000)
    paper_client.get_ticker.assert_awaited_once_with("BTCUSDT")


@pytest.mark.asyncio
async def test_get_account_info(paper_client: PaperExchangeClient) -> None:
    info = await paper_client.get_account_info()
    assert info["totalWalletBalance"] == "10000"
    assert info["availableBalance"] == "10000"
    assert info["totalUnrealizedProfit"] == "0"


@pytest.mark.asyncio
async def test_get_asset_balance_usdt(
    paper_client: PaperExchangeClient,
) -> None:
    balance = await paper_client.get_asset_balance("USDT")
    assert balance["asset"] == "USDT"
    assert balance["balance"] == "10000"
    assert balance["availableBalance"] == "10000"


@pytest.mark.asyncio
async def test_get_asset_balance_other(
    paper_client: PaperExchangeClient,
) -> None:
    balance = await paper_client.get_asset_balance("BTC")
    assert balance["asset"] == "BTC"
    assert balance["balance"] == "0"
    assert balance["availableBalance"] == "0"


@pytest.mark.asyncio
async def test_take_profit_order_stored_as_new(
    paper_client: PaperExchangeClient,
) -> None:
    result = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.TAKE_PROFIT_MARKET,
        quantity=Decimal("0.1"),
        stop_price=Decimal(55000),
        reduce_only=True,
    )

    assert result.status == OrderStatus.NEW
    assert paper_client.balance_usdt == Decimal(10000)


@pytest.mark.asyncio
async def test_leverage_affects_margin(
    paper_client: PaperExchangeClient,
) -> None:
    """Setting leverage reduces required margin."""
    await paper_client.futures_change_leverage("BTCUSDT", 10)

    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal(50000),
        time_in_force=TimeInForce.GTC,
    )

    # margin = 0.1 * 50000 / 10 = 500, commission = 5
    expected = Decimal(10000) - Decimal(500) - Decimal(5)
    assert paper_client.balance_usdt == expected


@pytest.mark.asyncio
async def test_short_then_close_with_profit(
    paper_client: PaperExchangeClient,
) -> None:
    """Open SHORT, then close (BUY) at a lower price for profit."""
    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
    )
    after_short = paper_client.balance_usdt

    exit_ticker = TickerSchema(symbol="BTCUSDT", last_price=Decimal(49000))
    paper_client.get_ticker = AsyncMock(return_value=exit_ticker)

    await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
    )
    after_close = paper_client.balance_usdt

    assert after_close > after_short


def test_unrealized_pnl_long_position() -> None:
    """Unrealized PnL computed from cached prices for LONG positions."""
    with patch("kavzi_trader.api.binance.client.BinanceAPIClient"):
        client = PaperExchangeClient()
    client._positions["BTCUSDT"] = _PaperPositionTracker(
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.1"),
        entry_price=Decimal(50000),
        leverage=3,
        margin=Decimal("1666.67"),
    )
    client._last_prices["BTCUSDT"] = Decimal(51000)
    pnl = client._calculate_total_unrealized_pnl()
    # (51000 - 50000) * 0.1 = 100
    assert pnl == Decimal(100)


def test_unrealized_pnl_short_position() -> None:
    """Unrealized PnL computed from cached prices for SHORT positions."""
    with patch("kavzi_trader.api.binance.client.BinanceAPIClient"):
        client = PaperExchangeClient()
    client._positions["DOGEUSDT"] = _PaperPositionTracker(
        symbol="DOGEUSDT",
        side="SHORT",
        quantity=Decimal(86207),
        entry_price=Decimal("0.09055"),
        leverage=1,
        margin=Decimal(7810),
    )
    client._last_prices["DOGEUSDT"] = Decimal("0.09008")
    pnl = client._calculate_total_unrealized_pnl()
    # (0.09055 - 0.09008) * 86207 = ~40.52
    expected = (Decimal("0.09055") - Decimal("0.09008")) * Decimal(86207)
    assert pnl == expected
    assert pnl > Decimal(0)


def test_unrealized_pnl_no_cached_price() -> None:
    """Positions without a cached price contribute zero PnL."""
    with patch("kavzi_trader.api.binance.client.BinanceAPIClient"):
        client = PaperExchangeClient()
    client._positions["BTCUSDT"] = _PaperPositionTracker(
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.1"),
        entry_price=Decimal(50000),
        leverage=1,
        margin=Decimal(5000),
    )
    # No price cached
    assert client._calculate_total_unrealized_pnl() == Decimal(0)
