from decimal import Decimal

import pytest

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.order_flow.open_interest import (
    calculate_oi_momentum,
    oi_period_minutes,
    periods_for_oi_period,
)
from kavzi_trader.order_flow.schemas import OpenInterestSchema


def test_calculate_oi_momentum_with_valid_data(sample_oi_history):
    result = calculate_oi_momentum(sample_oi_history, periods_24h=12)

    assert result is not None
    assert result.open_interest == sample_oi_history[-1].open_interest
    assert isinstance(result.oi_change_1h_percent, Decimal)
    assert isinstance(result.oi_change_24h_percent, Decimal)


def test_calculate_oi_momentum_returns_none_with_empty_list():
    result = calculate_oi_momentum([])

    assert result is None


def test_calculate_oi_momentum_without_1h_history_returns_none():
    history = [
        OpenInterestSchema(
            symbol="BTCUSDT",
            open_interest=Decimal(100000),
            timestamp=utc_now(),
        ),
    ]

    assert calculate_oi_momentum(history) is None


def test_calculate_oi_momentum_24h_is_none_when_history_too_short(sample_oi_history):
    # 13 samples cover 1h but not the default 96-period (24h) lookback.
    result = calculate_oi_momentum(sample_oi_history)

    assert result is not None
    assert result.oi_change_1h_percent != Decimal(0)
    assert result.oi_change_24h_percent is None


def test_calculate_oi_momentum_24h_uses_full_lookback():
    # 97 samples at 15m: index 0 is exactly 24h before the last one.
    history = [
        OpenInterestSchema(
            symbol="BTCUSDT",
            open_interest=Decimal(1000 + 10 * i),
            timestamp=utc_now(),
        )
        for i in range(97)
    ]

    result = calculate_oi_momentum(history, periods_1h=4, periods_24h=96)

    assert result is not None
    # (1960 - 1000) / 1000 = 96%
    assert result.oi_change_24h_percent == Decimal("96.00")


@pytest.mark.parametrize(
    ("interval_minutes", "expected_period"),
    [(1, 5), (5, 5), (15, 15), (30, 30), (60, 30), (240, 30)],
)
def test_oi_period_minutes_picks_supported_period(interval_minutes, expected_period):
    assert oi_period_minutes(interval_minutes) == expected_period


def test_oi_period_minutes_rejects_non_positive_interval():
    with pytest.raises(ValueError, match="interval_minutes"):
        oi_period_minutes(0)


def test_periods_for_oi_period_15m():
    assert periods_for_oi_period(15) == (4, 96)


def test_calculate_oi_momentum_positive_change(sample_oi_history):
    result = calculate_oi_momentum(sample_oi_history, periods_1h=5, periods_24h=10)

    assert result is not None
    assert result.oi_change_1h_percent > 0


def test_calculate_oi_momentum_with_custom_periods():
    from datetime import timedelta

    from kavzi_trader.commons.time_utility import utc_now

    base_time = utc_now()
    history = [
        OpenInterestSchema(
            symbol="BTCUSDT",
            open_interest=Decimal(str(100000 + i * 1000)),
            timestamp=base_time + timedelta(minutes=5 * i),
        )
        for i in range(20)
    ]

    result = calculate_oi_momentum(history, periods_1h=6, periods_24h=12)

    assert result is not None
    expected_1h_change = ((119000 - 113000) / 113000) * 100
    assert abs(float(result.oi_change_1h_percent) - expected_1h_change) < 0.1
