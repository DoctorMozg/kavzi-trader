from pathlib import Path

import numpy as np
import pytest

from kavzi_trader.evals.validation.backtest_overfitting import BacktestOverfitting
from kavzi_trader.evals.validation.sharpe_deflation import SharpeDeflation
from kavzi_trader.evals.validation.trial_analyzer import TrialAnalyzer
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema


def trial(
    variant: str, mean: float, seed: int, *, family: str = "trend", days: str = "a"
) -> TrialSchema:
    returns = np.random.default_rng(seed).normal(mean, 0.01, 400)
    return TrialSchema(
        family=family,
        variant=variant,
        first_day=f"{days}-start",
        last_day=f"{days}-end",
        daily_net=returns.tolist(),
    )


@pytest.fixture
def registry(tmp_path: Path) -> TrialRegistry:
    return TrialRegistry(tmp_path / "evals" / "trials.jsonl")


class TestTrialRegistry:
    def test_rerunning_a_variant_over_the_same_days_is_not_a_new_trial(
        self, registry: TrialRegistry
    ) -> None:
        assert registry.record(trial("L20", 0.001, 1))
        assert not registry.record(trial("L20", 0.002, 2))
        assert registry.record(trial("L20", 0.001, 1, days="b"))

        assert len(registry.trials("trend")) == 2

    def test_trials_are_read_back_per_family(self, registry: TrialRegistry) -> None:
        registry.record(trial("L20", 0.001, 1))
        registry.record(trial("x", 0.001, 1, family="funding"))

        [only] = registry.trials("funding")
        assert only.variant == "x"
        assert only.daily_net == trial("x", 0.001, 1).daily_net

    def test_an_empty_registry_has_no_trials(self, registry: TrialRegistry) -> None:
        assert registry.trials("trend") == []


class TestTrialAnalyzer:
    @pytest.fixture
    def analyzer(self) -> TrialAnalyzer:
        return TrialAnalyzer(SharpeDeflation(), BacktestOverfitting(n_blocks=8))

    def test_best_trial_is_deflated_by_every_trial(
        self, analyzer: TrialAnalyzer
    ) -> None:
        trials = [trial(f"v{i}", 0.0, i) for i in range(10)]
        trials.append(trial("other window", 0.0, 99, days="b"))
        trials.append(trial("winner", 0.003, 100))

        summary = analyzer.summarize(trials)

        assert summary.best_variant == "winner"
        assert summary.n_trials == 12
        assert summary.deflated.n_trials == 12
        assert summary.pbo is not None
        assert summary.pbo_trials == 11

    def test_a_lone_window_has_no_pbo(self, analyzer: TrialAnalyzer) -> None:
        summary = analyzer.summarize([trial("only", 0.001, 1)])

        assert summary.pbo is None
        assert summary.deflated.expected_max_sharpe == 0
