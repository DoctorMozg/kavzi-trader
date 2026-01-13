from decimal import Decimal

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


def test_calculator_uses_default_long_short_ratio_when_none(
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
    assert result.long_short_ratio == Decimal("1.0")
    assert result.long_account_percent == Decimal("50.0")


def test_calculator_computed_fields(sample_funding_rates, sample_oi_history):
    calculator = OrderFlowCalculator()

    result = calculator.calculate(
        symbol="BTCUSDT",
        funding_rates=sample_funding_rates,
        oi_history=sample_oi_history,
    )

    assert result is not None
    assert isinstance(result.is_crowded_long, bool)
    assert isinstance(result.is_crowded_short, bool)
    assert isinstance(result.squeeze_alert, bool)


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
