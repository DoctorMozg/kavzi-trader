import numpy as np
import pytest

from kavzi_trader.evals.validation.backtest_overfitting import BacktestOverfitting


@pytest.fixture
def cscv() -> BacktestOverfitting:
    return BacktestOverfitting(n_blocks=10)


class TestProbabilityOfOverfitting:
    def test_zero_sum_trials_always_lose_out_of_sample(
        self, cscv: BacktestOverfitting
    ) -> None:
        # Each trial's full-sample mean is zero, so in-sample gains are
        # exactly out-of-sample losses: the in-sample winner ranks low.
        noise = np.random.default_rng(4).normal(0, 0.01, size=(1000, 30))
        zero_sum = noise - noise.mean(axis=0)

        result = cscv.probability(zero_sum)

        assert result.n_combinations == 252
        assert result.pbo > 0.9

    def test_one_skilled_trial_among_noise_does_not_overfit(
        self, cscv: BacktestOverfitting
    ) -> None:
        returns = np.random.default_rng(5).normal(0, 0.01, size=(1000, 30))
        returns[:, 7] += 0.004

        assert cscv.probability(returns).pbo < 0.05

    def test_leftover_oldest_periods_are_dropped(
        self, cscv: BacktestOverfitting
    ) -> None:
        returns = np.random.default_rng(6).normal(0, 0.01, size=(1007, 5))

        assert cscv.probability(returns).logits == cscv.probability(returns[7:]).logits

    @pytest.mark.parametrize("n_blocks", [0, 3])
    def test_block_count_must_be_even(self, n_blocks: int) -> None:
        with pytest.raises(ValueError, match="even"):
            BacktestOverfitting(n_blocks)

    def test_one_trial_is_not_a_selection(self, cscv: BacktestOverfitting) -> None:
        with pytest.raises(ValueError, match="2 trials"):
            cscv.probability(np.zeros((100, 1)))
