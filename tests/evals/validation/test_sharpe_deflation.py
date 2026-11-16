import math

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.validation.sharpe_deflation import SharpeDeflation

# Bailey & Lopez de Prado (2014) worked example: annual SR 2.5 and trial
# variance 1/2 over 250 periods a year, five years of daily returns.
PAPER_SR = 2.5 / math.sqrt(250)
PAPER_VARIANCE = 1 / (2 * 250)


@pytest.fixture
def deflation() -> SharpeDeflation:
    return SharpeDeflation()


class TestPaperExample:
    def test_expected_max_of_100_trials(self, deflation: SharpeDeflation) -> None:
        assert deflation.expected_max_sharpe(100, PAPER_VARIANCE) == pytest.approx(
            0.1132, abs=5e-4
        )

    @pytest.mark.parametrize(
        ("n_trials", "skew", "kurtosis", "expected"),
        [(100, -3, 10, 0.9004), (46, -3, 10, 0.9505), (88, 0, 3, 0.9505)],
    )
    def test_deflated_sharpe(
        self,
        deflation: SharpeDeflation,
        n_trials: int,
        skew: float,
        kurtosis: float,
        expected: float,
    ) -> None:
        threshold = deflation.expected_max_sharpe(n_trials, PAPER_VARIANCE)

        dsr = deflation.probabilistic_sharpe(PAPER_SR, threshold, 1250, skew, kurtosis)

        assert dsr == pytest.approx(expected, abs=1e-3)


class TestDeflateReturns:
    def test_one_trial_is_judged_against_zero(self, deflation: SharpeDeflation) -> None:
        returns = pd.Series(np.random.default_rng(1).normal(0.001, 0.01, 1000))

        result = deflation.deflate(returns, [0.1])

        assert result.expected_max_sharpe == 0
        assert result.deflated_sharpe == pytest.approx(
            deflation.probabilistic_sharpe(
                result.sharpe, 0, 1000, returns.skew(), returns.kurt() + 3
            )
        )

    def test_more_trials_deflate_the_same_returns_further(
        self, deflation: SharpeDeflation
    ) -> None:
        rng = np.random.default_rng(2)
        returns = pd.Series(rng.normal(0.001, 0.01, 1000))
        few = list(rng.normal(0, 0.05, 5))
        many = list(rng.normal(0, 0.05, 500))

        assert (
            deflation.deflate(returns, many).deflated_sharpe
            < deflation.deflate(returns, few).deflated_sharpe
        )

    def test_constant_returns_are_rejected(self, deflation: SharpeDeflation) -> None:
        with pytest.raises(ValueError, match="non-constant"):
            deflation.deflate(pd.Series([0.01] * 10), [0.1])
