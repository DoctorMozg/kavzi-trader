from decimal import Decimal

import pytest

from kavzi_trader.order_flow.calculator import OrderFlowCalculator


def test_calculator_returns_valid_schema(
    sample_funding_rates,
    sample_oi_history,
    sample_long_short_ratio,
):
    calculator = OrderFlowCalculator()

    result = calculator.calculate(
        symbol="BTCUSDT",
        funding_rates=sample_funding_rates,
        oi_history=sample_oi_history,
        long_short_ratio=sample_long_short_ratio,
    )

    assert result is not None
    assert result.symbol == "BTCUSDT"
    assert result.funding_rate == sample_funding_rates[-1].funding_rate
    assert result.open_interest == sample_oi_history[-1].open_interest
    assert result.long_short_ratio == sample_long_short_ratio.long_short_ratio


def test_calculator_returns_none_with_insufficient_funding_rates(sample_oi_history):
    calculator = OrderFlowCalculator()

    result = calculator.calculate(
        symbol="BTCUSDT",
        funding_rates=[],
        oi_history=sample_oi_history,
    )

    assert result is None


def test_calculator_returns_none_with_empty_oi_history(sample_funding_rates):
    calculator = OrderFlowCalculator()

    result = calculator.calculate(
        symbol="BTCUSDT",
        funding_rates=sample_funding_rates,
        oi_history=[],
    )

    assert result is None


def test_calculator_leaves_long_short_none_when_no_data(
    sample_funding_rates,
    sample_oi_history,
):
    calculator = OrderFlowCalculator()

    result = calculator.calculate(
        symbol="BTCUSDT",
        funding_rates=sample_funding_rates,
        oi_history=sample_oi_history,
        long_short_ratio=None,
    )

    assert result is not None
    assert result.long_short_ratio is None
    assert result.long_account_percent is None
    assert result.short_account_percent is None


def test_calculator_computed_fields(sample_funding_rates, sample_oi_history):
    calculator = OrderFlowCalculator()

    result = calculator.calculate(
        symbol="BTCUSDT",
        funding_rates=sample_funding_rates,
        oi_history=sample_oi_history,
        price_change_1h_percent=Decimal("0.2"),
    )

    # Fixture: zscore ~1.72 (below crowded threshold), OI +9.77% 1h, price +0.2%
    assert result is not None
    assert result.is_crowded_long is False
    assert result.is_crowded_short is False
    assert result.squeeze_alert is True
    assert result.oi_funding_divergence is False


def test_calculator_squeeze_alert_off_without_price_change(
    sample_funding_rates,
    sample_oi_history,
):
    result = OrderFlowCalculator().calculate(
        symbol="BTCUSDT",
        funding_rates=sample_funding_rates,
        oi_history=sample_oi_history,
    )

    assert result is not None
    assert result.squeeze_alert is False


def test_calculator_with_price_change(sample_funding_rates, sample_oi_history):
    calculator = OrderFlowCalculator()

    result = calculator.calculate(
        symbol="BTCUSDT",
        funding_rates=sample_funding_rates,
        oi_history=sample_oi_history,
        price_change_1h_percent=Decimal("0.2"),
    )

    assert result is not None
    assert result.price_change_1h_percent == Decimal("0.2")


@pytest.mark.parametrize(
    ("interval_minutes", "period", "limit"),
    [(15, "15m", 97), (1, "5m", 289), (60, "30m", 49)],
)
def test_calculator_oi_request_covers_24h(interval_minutes, period, limit):
    calculator = OrderFlowCalculator(interval_minutes=interval_minutes)

    assert calculator.oi_period == period
    assert calculator.oi_history_limit == limit


def test_calculator_24h_change_is_none_without_24h_history(
    sample_funding_rates,
    sample_oi_history,
):
    result = OrderFlowCalculator().calculate(
        symbol="BTCUSDT",
        funding_rates=sample_funding_rates,
        oi_history=sample_oi_history,
    )

    assert result is not None
    assert result.oi_change_24h_percent is None
