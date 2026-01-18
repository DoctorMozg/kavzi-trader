from datetime import UTC, datetime, timedelta
from decimal import Decimal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.movement import MinimumMovementFilter


def test_movement_blocks_small_body() -> None:
    config = FilterConfigSchema()
    movement_filter = MinimumMovementFilter(config)
    now = datetime(2025, 1, 6, 12, 0, tzinfo=UTC)
    candle = CandlestickSchema(
        open_time=now - timedelta(minutes=5),
        open_price=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100.1"),
        volume=Decimal("1000"),
        close_time=now,
        quote_volume=Decimal("100000"),
        trades_count=100,
        taker_buy_base_volume=Decimal("500"),
        taker_buy_quote_volume=Decimal("50000"),
        interval="5m",
        symbol="BTCUSDT",
    )

    result = movement_filter.evaluate(candle=candle, atr=Decimal("10"))

    assert result.is_allowed is False, "Expected movement filter to block"


def test_movement_allows_normal_body(sample_candle) -> None:
    config = FilterConfigSchema()
    movement_filter = MinimumMovementFilter(config)

    result = movement_filter.evaluate(candle=sample_candle, atr=Decimal("5"))

    assert result.is_allowed is True, "Expected movement filter to allow"
