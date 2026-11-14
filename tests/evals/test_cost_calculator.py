import logging

import pytest

from kavzi_trader.evals.cost_calculator import CostCalculator
from kavzi_trader.evals.token_usage_schema import TokenUsageSchema


class TestCostCalculator:
    def test_sonnet_prices_each_token_class_separately(self) -> None:
        usage = TokenUsageSchema(
            input_tokens=1_000_000 + 500_000 + 100_000,
            output_tokens=200_000,
            cache_read_tokens=500_000,
            cache_write_tokens=100_000,
        )

        cost = CostCalculator().cost_usd("claude-sonnet-5-5", usage)

        # 1M fresh in + 0.2M out + 0.5M read + 0.1M write
        assert cost == pytest.approx(2.0 + 2.0 + 0.05 + 0.25)

    def test_opus_is_priced_higher_than_sonnet(self) -> None:
        usage = TokenUsageSchema(input_tokens=1_000_000, output_tokens=1_000_000)

        assert CostCalculator().cost_usd("claude-opus-5-5", usage) == pytest.approx(
            24.0
        )

    def test_unknown_model_gives_none_and_warns_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        calculator = CostCalculator()
        usage = TokenUsageSchema(input_tokens=10, output_tokens=10)

        with caplog.at_level(logging.WARNING):
            assert calculator.cost_usd("mystery-model", usage) is None
            assert calculator.cost_usd("mystery-model", usage) is None

        assert len([r for r in caplog.records if "mystery-model" in r.message]) == 1

    def test_zero_usage_costs_nothing(self) -> None:
        assert CostCalculator().cost_usd(
            "claude-opus-5-5", TokenUsageSchema()
        ) == pytest.approx(0.0)
