import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.barrier_enums import CaseLabel
from kavzi_trader.evals.case_sampler import CaseSampler

REGIMES = ["LOW", "NORMAL", "HIGH", "EXTREME"]
SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]
SPACING = 96


def _candidates(seed: int = 0, bars: int = 6000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for symbol in SYMBOLS:
        for i in range(500, bars, 3):
            rows.append(
                (
                    symbol,
                    i,
                    rng.choice(["LONG", "SHORT", "NO_TRADE"]),
                    rng.choice(REGIMES, p=[0.1, 0.6, 0.2, 0.1]),
                )
            )
    return pd.DataFrame(rows, columns=["symbol", "bar_index", "label", "regime"])


def _sampler(seed: int = 42, n: int = 60) -> CaseSampler:
    return CaseSampler(n, seed, SPACING, REGIMES)


class TestCaseSampler:
    def test_same_seed_gives_identical_sample(self) -> None:
        data = _candidates()
        assert _sampler().sample(data) == _sampler().sample(data)

    def test_different_seed_changes_sample(self) -> None:
        data = _candidates()
        assert _sampler(1).sample(data) != _sampler(2).sample(data)

    def test_labels_are_balanced(self) -> None:
        picked = _sampler(n=61).sample(_candidates())
        counts = pd.Series([p.label for p in picked]).value_counts()
        assert counts[CaseLabel.LONG] == 21
        assert counts[CaseLabel.SHORT] == 20
        assert counts[CaseLabel.NO_TRADE] == 20

    def test_regimes_and_symbols_are_spread_evenly(self) -> None:
        picked = _sampler(n=120).sample(_candidates())
        for label in CaseLabel:
            mine = [p for p in picked if p.label is label]
            regimes = pd.Series([p.regime for p in mine]).value_counts()
            assert regimes.max() - regimes.min() <= 1
            symbols = pd.Series([p.symbol for p in mine]).value_counts()
            assert symbols.max() - symbols.min() <= 2

    def test_same_symbol_cases_never_overlap(self) -> None:
        picked = _sampler(n=150).sample(_candidates())
        for symbol in SYMBOLS:
            bars = sorted(p.bar_index for p in picked if p.symbol == symbol)
            gaps = np.diff(bars)
            assert (gaps >= SPACING).all()

    def test_reports_shortfall_instead_of_relaxing_spacing(self) -> None:
        # One symbol with room for only ~2 spaced cases per label.
        data = pd.DataFrame(
            {
                "symbol": "AAA",
                "bar_index": range(0, 300, 10),
                "label": ["LONG", "SHORT", "NO_TRADE"] * 10,
                "regime": "NORMAL",
            }
        )
        picked = CaseSampler(30, 0, SPACING, REGIMES).sample(data)
        bars = sorted(p.bar_index for p in picked)
        assert len(picked) < 30
        assert (np.diff(bars) >= SPACING).all()

    def test_rejects_nonpositive_case_count(self) -> None:
        with pytest.raises(ValueError, match="n_cases"):
            CaseSampler(0, 1, SPACING, REGIMES)
