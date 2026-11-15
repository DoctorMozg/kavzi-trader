import numpy as np
import pytest

from kavzi_trader.evals.trend_portfolio import TrendPortfolio

HELD = np.array([[0.2, 0.0], [0.2, -0.1]])
RETURNS = np.array([[0.01, 0.02], [-0.02, 0.05]])
FUNDING = np.array([[0.0003, 0.0001], [0.0003, -0.0002]])


@pytest.fixture
def portfolio() -> TrendPortfolio:
    return TrendPortfolio(commission_rate=0.001)


class TestTrendPortfolio:
    def test_traded_weight_is_change_from_previous_row_starting_flat(
        self, portfolio: TrendPortfolio
    ) -> None:
        run = portfolio.run(HELD, RETURNS, FUNDING)

        assert run.traded.tolist() == pytest.approx([0.2, 0.1])
        assert run.cost.tolist() == pytest.approx([0.0002, 0.0001])

    def test_long_pays_funding_and_short_receives_it(
        self, portfolio: TrendPortfolio
    ) -> None:
        run = portfolio.run(HELD, RETURNS, FUNDING)

        # Day 2: long 0.2 pays 0.00006, short -0.1 at negative funding pays 0.00002.
        assert run.funding.tolist() == pytest.approx([0.00006, 0.00008])

    def test_net_is_gross_minus_cost_minus_funding(
        self, portfolio: TrendPortfolio
    ) -> None:
        run = portfolio.run(HELD, RETURNS, FUNDING)

        assert run.gross.tolist() == pytest.approx([0.002, -0.009])
        assert run.net.tolist() == pytest.approx([0.00174, -0.00918])

    def test_rejects_mismatched_shapes(self, portfolio: TrendPortfolio) -> None:
        with pytest.raises(ValueError, match="shape mismatch"):
            portfolio.run(HELD, RETURNS[:1], FUNDING)
