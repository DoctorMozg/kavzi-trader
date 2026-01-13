from decimal import Decimal

from kavzi_trader.order_flow.open_interest import calculate_oi_momentum
from kavzi_trader.order_flow.schemas import OpenInterestSchema


def test_calculate_oi_momentum_with_valid_data(sample_oi_history):
    result = calculate_oi_momentum(sample_oi_history)

    assert result is not None
    assert result.open_interest == sample_oi_history[-1].open_interest
    assert isinstance(result.oi_change_1h_percent, Decimal)
    assert isinstance(result.oi_change_24h_percent, Decimal)


def test_calculate_oi_momentum_returns_none_with_empty_list():
    result = calculate_oi_momentum([])

    assert result is None


def test_calculate_oi_momentum_with_short_history():
    from kavzi_trader.commons.time_utility import utc_now

    short_history = [
        OpenInterestSchema(
            symbol="BTCUSDT",
            open_interest=Decimal("100000"),
            timestamp=utc_now(),
        ),
    ]

    result = calculate_oi_momentum(short_history)

    assert result is not None
    assert result.open_interest == Decimal("100000")
    assert result.oi_change_1h_percent == Decimal("0")
    assert result.oi_change_24h_percent == Decimal("0")


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
