from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.orchestrator.providers.live_order_flow_fetcher import (
    LiveOrderFlowFetcher,
)
from kavzi_trader.order_flow.schemas import OrderFlowSchema


def _build_candle(close_time: datetime, close_price: Decimal) -> CandlestickSchema:
    return CandlestickSchema(
        open_time=close_time - timedelta(minutes=1),
        open_price=close_price,
        high_price=close_price,
        low_price=close_price,
        close_price=close_price,
        volume=Decimal(1),
        close_time=close_time,
        quote_volume=Decimal(1),
        trades_count=1,
        taker_buy_base_volume=Decimal("0.5"),
        taker_buy_quote_volume=Decimal("0.5"),
        interval="1m",
        symbol="BTCUSDT",
    )


@pytest.mark.asyncio
async def test_fetch_symbol_uses_full_hour_price_change_for_1m() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [
        _build_candle(start + timedelta(minutes=minute), Decimal(str(100 + minute)))
        for minute in range(61)
    ]
    timestamp_ms = int(start.timestamp() * 1000)

    exchange = AsyncMock()
    exchange.get_funding_rate = AsyncMock(
        return_value=[
            {
                "fundingRate": "0.0001",
                "fundingTime": timestamp_ms,
                "markPrice": "100.0",
            },
        ],
    )
    exchange.get_open_interest_history = AsyncMock(
        return_value=[
            {
                "sumOpenInterest": "1000",
                "timestamp": timestamp_ms,
            },
        ],
    )
    exchange.get_long_short_ratio = AsyncMock(
        return_value=[
            {
                "longShortRatio": "1.1",
                "longAccount": "0.55",
                "shortAccount": "0.45",
                "timestamp": timestamp_ms,
            },
        ],
    )

    cache = Mock()
    cache.get_candles.return_value = candles
    cache.update_order_flow = AsyncMock()

    calculator = Mock()
    calculator.calculate = Mock(
        return_value=OrderFlowSchema(
            symbol="BTCUSDT",
            timestamp=start,
            funding_rate=Decimal("0.0001"),
            funding_zscore=Decimal(0),
            next_funding_time=start,
            open_interest=Decimal(1000),
            oi_change_1h_percent=Decimal(0),
            oi_change_24h_percent=Decimal(0),
            long_short_ratio=Decimal("1.1"),
            long_account_percent=Decimal("0.55"),
            short_account_percent=Decimal("0.45"),
            price_change_1h_percent=Decimal(0),
        ),
    )

    fetcher = LiveOrderFlowFetcher(
        exchange=exchange,
        cache=cache,
        calculator=calculator,
        symbols=["BTCUSDT"],
    )

    await fetcher._fetch_symbol("BTCUSDT")

    assert calculator.calculate.call_args.kwargs["price_change_1h_percent"] == Decimal(
        60,
    )


@pytest.mark.asyncio
async def test_fetch_symbol_skips_price_change_when_hour_anchor_is_missing() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [_build_candle(start - timedelta(minutes=1), Decimal(99))]
    candles.extend(
        _build_candle(start + timedelta(minutes=minute), Decimal(str(100 + minute)))
        for minute in range(2, 61)
    )
    timestamp_ms = int(start.timestamp() * 1000)

    exchange = AsyncMock()
    exchange.get_funding_rate = AsyncMock(
        return_value=[
            {
                "fundingRate": "0.0001",
                "fundingTime": timestamp_ms,
                "markPrice": "100.0",
            },
        ],
    )
    exchange.get_open_interest_history = AsyncMock(
        return_value=[
            {
                "sumOpenInterest": "1000",
                "timestamp": timestamp_ms,
            },
        ],
    )
    exchange.get_long_short_ratio = AsyncMock(
        return_value=[
            {
                "longShortRatio": "1.1",
                "longAccount": "0.55",
                "shortAccount": "0.45",
                "timestamp": timestamp_ms,
            },
        ],
    )

    cache = Mock()
    cache.get_candles.return_value = candles
    cache.update_order_flow = AsyncMock()

    calculator = Mock()
    calculator.calculate = Mock(
        return_value=OrderFlowSchema(
            symbol="BTCUSDT",
            timestamp=start,
            funding_rate=Decimal("0.0001"),
            funding_zscore=Decimal(0),
            next_funding_time=start,
            open_interest=Decimal(1000),
            oi_change_1h_percent=Decimal(0),
            oi_change_24h_percent=Decimal(0),
            long_short_ratio=Decimal("1.1"),
            long_account_percent=Decimal("0.55"),
            short_account_percent=Decimal("0.45"),
            price_change_1h_percent=None,
        ),
    )

    fetcher = LiveOrderFlowFetcher(
        exchange=exchange,
        cache=cache,
        calculator=calculator,
        symbols=["BTCUSDT"],
    )

    await fetcher._fetch_symbol("BTCUSDT")

    assert calculator.calculate.call_args.kwargs["price_change_1h_percent"] is None
