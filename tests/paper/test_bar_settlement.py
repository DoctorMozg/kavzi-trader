from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.order_enums import OrderSide, OrderStatus, OrderType
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.paper.costs_schema import PaperCostsSchema
from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.paper.sim_market_feed import SimMarketFeed

SYMBOL = "BTCUSDT"
BALANCE = Decimal(10_000)


def bar(open_: int, high: int, low: int, close: int) -> CandlestickSchema:
    moment = datetime(2021, 1, 1, tzinfo=UTC)
    return CandlestickSchema(
        open_time=moment,
        open_price=Decimal(open_),
        high_price=Decimal(high),
        low_price=Decimal(low),
        close_price=Decimal(close),
        volume=Decimal(1),
        close_time=moment,
        quote_volume=Decimal(1),
        trades_count=1,
        taker_buy_base_volume=Decimal(1),
        taker_buy_quote_volume=Decimal(1),
        symbol=SYMBOL,
    )


class Book:
    """A paper exchange priced by a simulated feed, with order helpers."""

    def __init__(self, costs: PaperCostsSchema | None = None) -> None:
        self.feed = SimMarketFeed()
        self.feed.set_price(SYMBOL, Decimal(100))
        self.exchange = PaperExchangeClient(
            initial_balance_usdt=BALANCE,
            costs=costs
            or PaperCostsSchema(taker_fee_rate=Decimal(0), maker_fee_rate=Decimal(0)),
            market_feed=self.feed,
        )

    async def open(self, side: OrderSide, qty: int, leverage: int = 1) -> None:
        await self.exchange.futures_change_leverage(SYMBOL, leverage)
        await self.exchange.create_order(SYMBOL, side, OrderType.MARKET, Decimal(qty))

    async def trigger(
        self, order_type: OrderType, side: OrderSide, price: int, qty: int = 1
    ) -> OrderResponseSchema:
        return await self.exchange.create_order(
            SYMBOL,
            side,
            order_type,
            Decimal(qty),
            stop_price=Decimal(price),
            reduce_only=True,
        )

    async def status(self, order: OrderResponseSchema) -> OrderResponseSchema:
        return await self.exchange.get_order(SYMBOL, order.order_id)


@pytest.fixture
def book() -> Book:
    return Book()


class TestStops:
    async def test_stop_gapped_through_fills_at_the_open(self, book: Book) -> None:
        await book.open(OrderSide.BUY, 1)
        stop = await book.trigger(OrderType.STOP_MARKET, OrderSide.SELL, 95)

        await book.exchange.on_bar(bar(90, 92, 88, 91))

        filled = await book.status(stop)
        assert filled.status == OrderStatus.FILLED
        assert filled.fills[0].price == Decimal(90)
        assert book.exchange.balance_usdt == BALANCE - 10

    async def test_stop_inside_the_range_fills_at_trigger_less_slippage(self) -> None:
        book = Book(
            PaperCostsSchema(taker_fee_rate=Decimal(0), slippage_bps=Decimal(10))
        )
        await book.open(OrderSide.BUY, 1)
        stop = await book.trigger(OrderType.STOP_MARKET, OrderSide.SELL, 95)

        await book.exchange.on_bar(bar(99, 101, 94, 96))

        assert (await book.status(stop)).fills[0].price == Decimal("94.905")

    async def test_short_stop_gapped_up_fills_at_the_open(self, book: Book) -> None:
        await book.open(OrderSide.SELL, 1)
        stop = await book.trigger(OrderType.STOP_MARKET, OrderSide.BUY, 105)

        await book.exchange.on_bar(bar(108, 110, 107, 109))

        assert (await book.status(stop)).fills[0].price == Decimal(108)

    async def test_bar_hitting_stop_and_target_fills_the_stop(self, book: Book) -> None:
        await book.open(OrderSide.BUY, 1)
        target = await book.trigger(OrderType.TAKE_PROFIT_MARKET, OrderSide.SELL, 110)
        stop = await book.trigger(OrderType.STOP_MARKET, OrderSide.SELL, 95)

        await book.exchange.on_bar(bar(100, 111, 94, 100))

        assert (await book.status(stop)).status == OrderStatus.FILLED
        assert (await book.status(target)).status == OrderStatus.CANCELED

    async def test_target_gapped_through_fills_at_its_trigger(self, book: Book) -> None:
        await book.open(OrderSide.BUY, 1)
        target = await book.trigger(OrderType.TAKE_PROFIT_MARKET, OrderSide.SELL, 110)

        await book.exchange.on_bar(bar(115, 116, 114, 115))

        assert (await book.status(target)).fills[0].price == Decimal(110)

    async def test_untouched_stop_stays_open(self, book: Book) -> None:
        await book.open(OrderSide.BUY, 1)
        stop = await book.trigger(OrderType.STOP_MARKET, OrderSide.SELL, 95)

        await book.exchange.on_bar(bar(100, 102, 96, 101))

        assert (await book.status(stop)).status == OrderStatus.NEW


async def test_resting_limit_touched_fills_at_its_price_as_maker() -> None:
    book = Book(PaperCostsSchema(taker_fee_rate=Decimal("0.0005")))
    limit = await book.exchange.create_order(
        SYMBOL, OrderSide.BUY, OrderType.LIMIT, Decimal(1), price=Decimal(97)
    )
    assert limit.status == OrderStatus.NEW

    await book.exchange.on_bar(bar(100, 101, 96, 98))

    filled = await book.status(limit)
    assert filled.fills[0].price == Decimal(97)
    assert filled.fills[0].commission == Decimal(97) * Decimal("0.0002")


class TestFunding:
    @pytest.mark.parametrize(
        ("side", "rate", "received"),
        [
            (OrderSide.BUY, "0.0001", "-0.02"),
            (OrderSide.SELL, "0.0001", "0.02"),
            (OrderSide.BUY, "-0.0001", "0.02"),
            (OrderSide.SELL, "-0.0001", "-0.02"),
        ],
    )
    async def test_positive_rate_moves_money_from_longs_to_shorts(
        self, book: Book, side: OrderSide, rate: str, received: str
    ) -> None:
        await book.open(side, 2)
        before = book.exchange.balance_usdt

        paid = await book.exchange.apply_funding(SYMBOL, Decimal(rate), Decimal(100))

        assert paid == Decimal(received)
        assert book.exchange.balance_usdt == before + Decimal(received)

    async def test_flat_book_pays_nothing(self, book: Book) -> None:
        paid = await book.exchange.apply_funding(SYMBOL, Decimal("0.01"), Decimal(100))

        assert paid == 0
        assert book.exchange.balance_usdt == BALANCE


class TestLiquidation:
    # 10x long from 100 with 0.4% maintenance margin liquidates at 90/0.996.

    async def _positions(self, book: Book) -> list[str]:
        return [p["symbol"] for p in await book.exchange.futures_get_position_info()]

    async def test_bar_through_liquidation_loses_the_margin(self, book: Book) -> None:
        await book.open(OrderSide.BUY, 1, leverage=10)
        info = await book.exchange.futures_get_position_info(SYMBOL)
        assert Decimal(info[0]["liquidationPrice"]) == Decimal(90) / Decimal("0.996")

        await book.exchange.on_bar(bar(99, 100, 90, 95))

        assert await self._positions(book) == []
        account = await book.exchange.get_account_info()
        assert Decimal(account["totalWalletBalance"]) == BALANCE - 10

    async def test_stop_above_liquidation_fills_first(self, book: Book) -> None:
        await book.open(OrderSide.BUY, 1, leverage=10)
        stop = await book.trigger(OrderType.STOP_MARKET, OrderSide.SELL, 95)

        await book.exchange.on_bar(bar(99, 100, 90, 95))

        assert (await book.status(stop)).status == OrderStatus.FILLED
        account = await book.exchange.get_account_info()
        assert Decimal(account["totalWalletBalance"]) == BALANCE - 5

    async def test_gap_below_liquidation_beats_the_stop(self, book: Book) -> None:
        await book.open(OrderSide.BUY, 1, leverage=10)
        stop = await book.trigger(OrderType.STOP_MARKET, OrderSide.SELL, 95)

        await book.exchange.on_bar(bar(89, 90, 85, 88))

        assert await self._positions(book) == []
        assert (await book.status(stop)).status == OrderStatus.CANCELED

    async def test_short_liquidates_on_the_high(self, book: Book) -> None:
        await book.open(OrderSide.SELL, 1, leverage=10)

        await book.exchange.on_bar(bar(101, 111, 100, 105))

        assert await self._positions(book) == []


async def test_bar_close_marks_the_position(book: Book) -> None:
    await book.open(OrderSide.BUY, 2)

    await book.exchange.on_bar(bar(100, 106, 99, 105))

    info = (await book.exchange.futures_get_position_info(SYMBOL))[0]
    assert Decimal(info["markPrice"]) == Decimal(105)
    assert Decimal(info["unRealizedProfit"]) == Decimal(10)
    account = await book.exchange.get_account_info()
    assert Decimal(account["totalUnrealizedProfit"]) == Decimal(10)
