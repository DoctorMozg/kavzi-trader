from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kavzi_trader.api.common.models import CandlestickSchema


@pytest.fixture
def sample_candles() -> list[CandlestickSchema]:
    base_time = datetime(2024, 1, 1, tzinfo=UTC)
    prices = [
        100,
        102,
        101,
        103,
        105,
        104,
        106,
        108,
        107,
        109,
        110,
        108,
        106,
        104,
        102,
        103,
        105,
        107,
        109,
        111,
        113,
        112,
        114,
        116,
        115,
        117,
        119,
        118,
        120,
        122,
        121,
        123,
        125,
        124,
        126,
        128,
        127,
        129,
        131,
        130,
        132,
        134,
        133,
        135,
        137,
        136,
        138,
        140,
        139,
        141,
    ]

    candles = []
    for i, price in enumerate(prices):
        open_time = base_time + timedelta(hours=i)
        close_time = open_time + timedelta(hours=1) - timedelta(seconds=1)

        high_adj = price * 1.01
        low_adj = price * 0.99

        candles.append(
            CandlestickSchema(
                open_time=open_time,
                close_time=close_time,
                open_price=Decimal(str(price - 0.5)),
                high_price=Decimal(str(high_adj)),
                low_price=Decimal(str(low_adj)),
                close_price=Decimal(str(price)),
                volume=Decimal(str(1000 + i * 10)),
                quote_volume=Decimal(str((1000 + i * 10) * price)),
                trades_count=100 + i,
                taker_buy_base_volume=Decimal(str(500 + i * 5)),
                taker_buy_quote_volume=Decimal(str((500 + i * 5) * price)),
            ),
        )
    return candles


@pytest.fixture
def trending_up_candles() -> list[CandlestickSchema]:
    base_time = datetime(2024, 1, 1, tzinfo=UTC)
    candles = []
    for i in range(50):
        price = 100 + i * 2
        open_time = base_time + timedelta(hours=i)
        close_time = open_time + timedelta(hours=1) - timedelta(seconds=1)

        candles.append(
            CandlestickSchema(
                open_time=open_time,
                close_time=close_time,
                open_price=Decimal(str(price - 1)),
                high_price=Decimal(str(price + 1)),
                low_price=Decimal(str(price - 2)),
                close_price=Decimal(str(price)),
                volume=Decimal(1000),
                quote_volume=Decimal(str(1000 * price)),
                trades_count=100,
                taker_buy_base_volume=Decimal(600),
                taker_buy_quote_volume=Decimal(str(600 * price)),
            ),
        )
    return candles


@pytest.fixture
def trending_down_candles() -> list[CandlestickSchema]:
    base_time = datetime(2024, 1, 1, tzinfo=UTC)
    candles = []
    for i in range(50):
        price = 200 - i * 2
        open_time = base_time + timedelta(hours=i)
        close_time = open_time + timedelta(hours=1) - timedelta(seconds=1)

        candles.append(
            CandlestickSchema(
                open_time=open_time,
                close_time=close_time,
                open_price=Decimal(str(price + 1)),
                high_price=Decimal(str(price + 2)),
                low_price=Decimal(str(price - 1)),
                close_price=Decimal(str(price)),
                volume=Decimal(1000),
                quote_volume=Decimal(str(1000 * price)),
                trades_count=100,
                taker_buy_base_volume=Decimal(400),
                taker_buy_quote_volume=Decimal(str(400 * price)),
            ),
        )
    return candles
