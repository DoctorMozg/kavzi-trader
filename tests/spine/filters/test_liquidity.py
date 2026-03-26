from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.liquidity import LiquidityFilter
from kavzi_trader.spine.filters.liquidity_period import LiquidityPeriod


def test_weekend_liquidity_multiplier() -> None:
    config = FilterConfigSchema()
    saturday = datetime(2025, 1, 4, 12, 0, tzinfo=UTC)
    liquidity_filter = LiquidityFilter(config, time_provider=lambda: saturday)

    result = liquidity_filter.evaluate()

    assert result.size_multiplier == Decimal("0.5"), "Expected weekend multiplier"
    assert result.period == LiquidityPeriod.LOW, "Expected low period on weekend"


def test_sunday_reopen_multiplier() -> None:
    config = FilterConfigSchema()
    sunday = datetime(2025, 1, 5, 21, 0, tzinfo=UTC)
    liquidity_filter = LiquidityFilter(config, time_provider=lambda: sunday)

    result = liquidity_filter.evaluate()

    assert result.size_multiplier == Decimal("0.8"), "Expected Sunday reopen multiplier"
    assert result.period == LiquidityPeriod.MEDIUM, (
        "Expected medium period after 20 UTC"
    )


def test_high_liquidity_session() -> None:
    config = FilterConfigSchema()
    weekday = datetime(2025, 1, 6, 14, 0, tzinfo=UTC)
    liquidity_filter = LiquidityFilter(config, time_provider=lambda: weekday)

    result = liquidity_filter.evaluate()

    assert result.size_multiplier == Decimal(
        "1.0",
    ), "Expected high liquidity multiplier"
    assert result.period == LiquidityPeriod.HIGH, "Expected high period during overlap"
