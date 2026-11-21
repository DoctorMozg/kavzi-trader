import numpy as np
import pytest

from kavzi_trader.evals.validation.paired_sharpe_test import PairedSharpeTest


@pytest.fixture
def base() -> list[float]:
    return list(np.random.default_rng(1).normal(0.0005, 0.02, 1000))


class TestPairedSharpeTest:
    def test_identical_series_differ_by_nothing(self, base: list[float]) -> None:
        result = PairedSharpeTest(resamples=200).compare(base, base)

        assert result.difference == 0
        assert result.lower == result.upper == 0
        assert result.p_not_better == 1

    def test_arm_with_added_daily_edge_is_better_in_every_resample(
        self, base: list[float]
    ) -> None:
        arm = [r + 0.002 for r in base]

        result = PairedSharpeTest(resamples=200).compare(base, arm)

        assert result.difference > 0
        assert 0 < result.lower < result.difference < result.upper
        assert result.p_not_better == 0

    def test_same_seed_gives_the_same_interval(self, base: list[float]) -> None:
        arm = list(np.random.default_rng(2).normal(0.0005, 0.02, 1000))

        first = PairedSharpeTest(resamples=100).compare(base, arm)
        second = PairedSharpeTest(resamples=100).compare(base, arm)

        assert first == second

    def test_misaligned_series_are_rejected(self, base: list[float]) -> None:
        with pytest.raises(ValueError, match="aligned"):
            PairedSharpeTest().compare(base, base[:-1])

    def test_higher_confidence_widens_the_interval(self, base: list[float]) -> None:
        arm = list(np.random.default_rng(2).normal(0.0005, 0.02, 1000))

        narrow = PairedSharpeTest(resamples=300).compare(base, arm)
        wide = PairedSharpeTest(resamples=300, confidence=0.99).compare(base, arm)

        assert wide.lower < narrow.lower
        assert wide.upper > narrow.upper
        assert (narrow.confidence, wide.confidence) == (0.90, 0.99)

    @pytest.mark.parametrize("confidence", [0.0, 1.0, 1.5])
    def test_confidence_outside_the_open_unit_interval_is_rejected(
        self, confidence: float
    ) -> None:
        with pytest.raises(ValueError, match="confidence"):
            PairedSharpeTest(confidence=confidence)
