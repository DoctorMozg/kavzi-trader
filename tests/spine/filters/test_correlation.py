from decimal import Decimal

from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.correlation import CorrelationFilter


def test_correlation_reduces_size(sample_positions) -> None:
    config = FilterConfigSchema()
    correlation_filter = CorrelationFilter(config)

    result = correlation_filter.evaluate(symbol="BTCUSDT", positions=sample_positions)

    assert result.size_multiplier == Decimal("0.5"), "Expected reduced size multiplier"
    assert result.reason == "correlated_exposure", "Expected correlation reason"


def test_correlation_allows_uncorrelated(sample_positions) -> None:
    config = FilterConfigSchema()
    correlation_filter = CorrelationFilter(config)

    result = correlation_filter.evaluate(symbol="SOLUSDT", positions=sample_positions)

    assert result.size_multiplier == Decimal("1.0"), "Expected full size multiplier"
