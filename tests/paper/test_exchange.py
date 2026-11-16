import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.exceptions import ExchangeError
from kavzi_trader.api.common.models import TickerSchema
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.domain.order_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from kavzi_trader.paper.exchange import PaperExchangeClient, _PaperPositionTrackerSchema


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
        price=Decimal(50000),
        time_in_force=TimeInForce.GTC,
    )

    fill = order.fills[0]
    expected_commission = Decimal("0.1") * Decimal(50000) * Decimal("0.001")
    assert fill.commission == expected_commission
    assert fill.commission_asset == "USDT"


@pytest.mark.asyncio
async def test_pullback_buy_limit_rests_below_market(
    paper_client: PaperExchangeClient,
) -> None:
    """A BUY limit below the ticker rests NEW instead of filling at market."""
    starting_balance = paper_client.balance_usdt
    order = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal(49000),
        time_in_force=TimeInForce.GTC,
    )

    assert order.status == OrderStatus.NEW
    assert order.executed_qty == Decimal(0)
    assert not order.fills
    # Nothing is locked or spent until the limit fills.
    assert paper_client.balance_usdt == starting_balance


@pytest.mark.asyncio
async def test_resting_buy_limit_fills_when_price_crosses(
    paper_client: PaperExchangeClient,
) -> None:
    """Polling a resting BUY limit fills it once the ticker touches its price."""
    order = await paper_client.create_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal(49000),
        time_in_force=TimeInForce.GTC,
    )
    assert order.status == OrderStatus.NEW

    # Price has not crossed yet: still resting.
    still_resting = await paper_client.get_order("BTCUSDT", order_id=order.order_id)
    assert still_resting.status == OrderStatus.NEW

    # Market drops to the limit: the next poll fills at the limit price.
    paper_client.get_ticker = AsyncMock(
        return_value=TickerSchema(symbol="BTCUSDT", last_price=Decimal(48000)),
    )
    filled = await paper_client.get_order("BTCUSDT", order_id=order.order_id)

    assert filled.status == OrderStatus.FILLED
    assert filled.executed_qty == Decimal("0.1")
    assert filled.fills[0].price == Decimal(49000)
    position = paper_client._positions["BTCUSDT"]
    assert position.side == "LONG"
    assert position.entry_price == Decimal(49000)


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
    client._positions["BTCUSDT"] = _PaperPositionTrackerSchema(
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
    client._positions["DOGEUSDT"] = _PaperPositionTrackerSchema(
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
    client._positions["BTCUSDT"] = _PaperPositionTrackerSchema(
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.1"),
        entry_price=Decimal(50000),
        leverage=1,
        margin=Decimal(5000),
    )
    # No price cached
    assert client._calculate_total_unrealized_pnl() == Decimal(0)


# ---- SEX-006: resting protective orders trigger on price cross --------------


def _set_price(client: PaperExchangeClient, price: int) -> None:
    client.get_ticker = AsyncMock(
        return_value=TickerSchema(symbol="BTCUSDT", last_price=Decimal(price)),
    )


async def _open_position(
    client: PaperExchangeClient,
    side: OrderSide,
) -> None:
    await client.create_order(
        symbol="BTCUSDT",
        side=side,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
    )


async def _place_protective(
    client: PaperExchangeClient,
    side: OrderSide,
    order_type: OrderType,
    stop_price: int,
) -> int:
    order = await client.create_order(
        symbol="BTCUSDT",
        side=side,
        order_type=order_type,
        quantity=Decimal("0.1"),
        stop_price=Decimal(stop_price),
        reduce_only=True,
    )
    return order.order_id


@pytest.mark.parametrize(
    ("entry_side", "exit_side", "order_type", "stop_price", "price", "fill_price"),
    [
        # LONG stop-loss: gap below the stop fills at the worse (lower) price.
        (
            OrderSide.BUY,
            OrderSide.SELL,
            OrderType.STOP_MARKET,
            49000,
            48500,
            48500,
        ),
        # LONG take-profit: fills at the trigger, not the better gap price.
        (
            OrderSide.BUY,
            OrderSide.SELL,
            OrderType.TAKE_PROFIT_MARKET,
            52000,
            52500,
            52000,
        ),
        # SHORT stop-loss: gap above the stop fills at the worse (higher) price.
        (
            OrderSide.SELL,
            OrderSide.BUY,
            OrderType.STOP_MARKET,
            51000,
            51500,
            51500,
        ),
        # SHORT take-profit
        (
            OrderSide.SELL,
            OrderSide.BUY,
            OrderType.TAKE_PROFIT_MARKET,
            48000,
            47500,
            48000,
        ),
    ],
)
@pytest.mark.asyncio
async def test_protective_order_fills_when_price_crosses_trigger(
    paper_client: PaperExchangeClient,
    entry_side: OrderSide,
    exit_side: OrderSide,
    order_type: OrderType,
    stop_price: int,
    price: int,
    fill_price: int,
) -> None:
    await _open_position(paper_client, entry_side)
    order_id = await _place_protective(paper_client, exit_side, order_type, stop_price)
    _set_price(paper_client, price)

    async with asyncio.timeout(2):
        order = await paper_client.get_order("BTCUSDT", order_id=order_id)

    assert order.status == OrderStatus.FILLED
    assert order.executed_qty == Decimal("0.1")
    assert order.effective_fill_price == Decimal(fill_price)
    assert paper_client._positions == {}
    assert await paper_client.get_open_orders("BTCUSDT") == []


@pytest.mark.parametrize(
    ("entry_side", "exit_side", "order_type", "stop_price", "price"),
    [
        (OrderSide.BUY, OrderSide.SELL, OrderType.STOP_MARKET, 49000, 49500),
        (OrderSide.BUY, OrderSide.SELL, OrderType.TAKE_PROFIT_MARKET, 52000, 51500),
        (OrderSide.SELL, OrderSide.BUY, OrderType.STOP_MARKET, 51000, 50500),
        (OrderSide.SELL, OrderSide.BUY, OrderType.TAKE_PROFIT_MARKET, 48000, 48500),
    ],
)
@pytest.mark.asyncio
async def test_protective_order_rests_while_price_inside_bracket(
    paper_client: PaperExchangeClient,
    entry_side: OrderSide,
    exit_side: OrderSide,
    order_type: OrderType,
    stop_price: int,
    price: int,
) -> None:
    await _open_position(paper_client, entry_side)
    order_id = await _place_protective(paper_client, exit_side, order_type, stop_price)
    _set_price(paper_client, price)

    order = await paper_client.get_order("BTCUSDT", order_id=order_id)

    assert order.status == OrderStatus.NEW
    assert "BTCUSDT" in paper_client._positions


@pytest.mark.asyncio
async def test_protective_fill_realizes_pnl_and_returns_margin(
    paper_client: PaperExchangeClient,
) -> None:
    await _open_position(paper_client, OrderSide.BUY)
    order_id = await _place_protective(
        paper_client,
        OrderSide.SELL,
        OrderType.TAKE_PROFIT_MARKET,
        52000,
    )
    _set_price(paper_client, 52000)

    await paper_client.get_order("BTCUSDT", order_id=order_id)

    # entry commission 5, exit commission 0.1 * 52000 * 0.001 = 5.2, pnl +200
    assert paper_client.balance_usdt == Decimal(10000) + 200 - 5 - Decimal("5.2")


@pytest.mark.asyncio
async def test_cancel_after_trigger_reports_order_already_filled(
    paper_client: PaperExchangeClient,
) -> None:
    await _open_position(paper_client, OrderSide.BUY)
    sl_id = await _place_protective(
        paper_client,
        OrderSide.SELL,
        OrderType.STOP_MARKET,
        49000,
    )
    _set_price(paper_client, 48900)

    with pytest.raises(ExchangeError) as exc_info:
        await paper_client.cancel_order("BTCUSDT", order_id=sl_id)

    assert exc_info.value.code == -2011
    filled = await paper_client.get_order("BTCUSDT", order_id=sl_id)
    assert filled.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_orphaned_protective_order_is_cancelled_not_raised(
    paper_client: PaperExchangeClient,
) -> None:
    await _open_position(paper_client, OrderSide.BUY)
    sl_id = await _place_protective(
        paper_client, OrderSide.SELL, OrderType.STOP_MARKET, 49000
    )
    tp_id = await _place_protective(
        paper_client, OrderSide.SELL, OrderType.TAKE_PROFIT_MARKET, 52000
    )
    _set_price(paper_client, 48900)
    await paper_client.get_order("BTCUSDT", order_id=sl_id)
    # Price rebounds through the TP trigger after the position is already flat.
    _set_price(paper_client, 52100)

    order = await paper_client.get_order("BTCUSDT", order_id=tp_id)

    assert order.status == OrderStatus.CANCELED
    assert paper_client._positions == {}


async def test_paper_client_satisfies_exchange_client_without_binance_inheritance(
    paper_client: PaperExchangeClient,
) -> None:
    # The annotations are the check: mypy rejects either assignment if a
    # protocol method is missing or has a different signature.
    paper: ExchangeClient = paper_client
    live: ExchangeClient = BinanceClient(api_key="", api_secret="")
    try:
        assert not isinstance(paper, BinanceClient)
        assert paper is paper_client
        assert live is not None
    finally:
        await live.close()


class TestResizingAnExistingPosition:
    """Grow, shrink and close of one LONG position (commission-free, 1x)."""

    @pytest.fixture
    def client(self, paper_client: PaperExchangeClient) -> PaperExchangeClient:
        paper_client._commission_rate = Decimal(0)
        return paper_client

    async def _trade(
        self,
        client: PaperExchangeClient,
        side: OrderSide,
        quantity: str,
        price: int,
        reduce_only: bool = False,
    ) -> None:
        client.get_ticker = AsyncMock(  # type: ignore[method-assign]
            return_value=TickerSchema(symbol="BTCUSDT", last_price=Decimal(price)),
        )
        await client.create_order(
            symbol="BTCUSDT",
            side=side,
            order_type=OrderType.MARKET,
            quantity=Decimal(quantity),
            reduce_only=reduce_only,
        )

    async def test_grow_averages_entry_and_adds_margin(
        self, client: PaperExchangeClient
    ) -> None:
        await self._trade(client, OrderSide.BUY, "1", 100)
        await self._trade(client, OrderSide.BUY, "3", 200)

        (info,) = await client.futures_get_position_info("BTCUSDT")
        assert Decimal(info["positionAmt"]) == 4
        assert Decimal(info["entryPrice"]) == Decimal(175)
        assert Decimal(info["isolatedMargin"]) == Decimal(700)
        assert client.balance_usdt == Decimal(10000) - 700

    async def test_shrink_realizes_pnl_and_keeps_entry(
        self, client: PaperExchangeClient
    ) -> None:
        await self._trade(client, OrderSide.BUY, "1", 100)
        await self._trade(client, OrderSide.BUY, "3", 200)
        await self._trade(client, OrderSide.SELL, "1", 250, reduce_only=True)

        (info,) = await client.futures_get_position_info("BTCUSDT")
        assert Decimal(info["positionAmt"]) == 3
        assert Decimal(info["entryPrice"]) == Decimal(175)
        assert Decimal(info["isolatedMargin"]) == Decimal(525)
        # 700 margin paid, 175 returned plus (250 - 175) profit
        assert client.balance_usdt == Decimal(10000) - 700 + 175 + 75

    async def test_full_close_flattens_and_returns_all_margin(
        self, client: PaperExchangeClient
    ) -> None:
        await self._trade(client, OrderSide.BUY, "1", 100)
        await self._trade(client, OrderSide.BUY, "3", 200)
        await self._trade(client, OrderSide.SELL, "4", 150, reduce_only=True)

        assert await client.futures_get_position_info("BTCUSDT") == []
        # (150 - 175) * 4 = -100 on 700 margin
        assert client.balance_usdt == Decimal(10000) - 100

    async def test_reduce_only_never_fills_past_the_position(
        self, client: PaperExchangeClient
    ) -> None:
        await self._trade(client, OrderSide.BUY, "1", 100)
        order = await client.create_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal(5),
            reduce_only=True,
        )

        assert order.executed_qty == Decimal(1)
        assert await client.futures_get_position_info("BTCUSDT") == []
