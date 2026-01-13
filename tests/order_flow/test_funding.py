from decimal import Decimal

from kavzi_trader.order_flow.funding import calculate_funding_zscore
from kavzi_trader.order_flow.schemas import FundingRateSchema


def test_calculate_funding_zscore_with_valid_data(sample_funding_rates):
    result = calculate_funding_zscore(sample_funding_rates)

    assert result is not None
    assert result.funding_rate == sample_funding_rates[-1].funding_rate
    assert isinstance(result.funding_zscore, Decimal)
    assert result.next_funding_time == sample_funding_rates[-1].funding_time


def test_calculate_funding_zscore_returns_none_with_insufficient_data():
    single_rate = [
        FundingRateSchema(
            symbol="BTCUSDT",
            funding_rate=Decimal("0.0001"),
            funding_time=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc,
            ),
        ),
    ]

    result = calculate_funding_zscore(single_rate)

    assert result is None


def test_calculate_funding_zscore_returns_none_with_empty_list():
    result = calculate_funding_zscore([])

    assert result is None


def test_calculate_funding_zscore_handles_zero_std():
    from datetime import timedelta

    from kavzi_trader.commons.time_utility import utc_now

    base_time = utc_now()
    constant_rates = [
        FundingRateSchema(
            symbol="BTCUSDT",
            funding_rate=Decimal("0.0001"),
            funding_time=base_time + timedelta(hours=i),
        )
        for i in range(5)
    ]

    result = calculate_funding_zscore(constant_rates)

    assert result is not None
    assert result.funding_zscore == Decimal("0")


def test_calculate_funding_zscore_with_custom_window(sample_funding_rates):
    result = calculate_funding_zscore(sample_funding_rates, window=5)

    assert result is not None
    assert isinstance(result.funding_zscore, Decimal)
