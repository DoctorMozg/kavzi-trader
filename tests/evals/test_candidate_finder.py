import numpy as np
import pytest

from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.evals.bracket_policy import BracketPolicy
from kavzi_trader.evals.market_feature_builder import MarketFeatureBuilder
from kavzi_trader.evals.symbol_candidates import SymbolCandidateFinder
from kavzi_trader.evals.triple_barrier import TripleBarrierLabeler
from tests.evals.frames import BASE_MS, STEP_MS, make_frame

HISTORY = 100
HORIZON = 10


@pytest.fixture
def finder() -> SymbolCandidateFinder:
    risk = RiskConfigSchema()
    return SymbolCandidateFinder(
        MarketFeatureBuilder(risk),
        BracketPolicy(risk),
        TripleBarrierLabeler(HORIZON),
        HISTORY,
        HORIZON,
        STEP_MS,
    )


class TestSymbolCandidateFinder:
    def test_excludes_warmup_and_trailing_horizon(
        self, finder: SymbolCandidateFinder
    ) -> None:
        frame = make_frame(400)
        found = finder.find(frame, window_start_ms=BASE_MS)
        assert found.entry_idx.min() == HISTORY - 1
        assert found.entry_idx.max() == len(frame) - HORIZON - 1

    def test_window_start_is_respected(self, finder: SymbolCandidateFinder) -> None:
        frame = make_frame(400)
        start = BASE_MS + 200 * STEP_MS
        found = finder.find(frame, window_start_ms=start)
        assert found.entry_idx.min() == 200

    def test_candidates_spanning_a_data_gap_are_dropped(
        self, finder: SymbolCandidateFinder
    ) -> None:
        frame = make_frame(400, skip={250})
        found = finder.find(frame, window_start_ms=BASE_MS)
        gap_pos = 250  # first row after the missing candle
        starts = found.entry_idx - (HISTORY - 1)
        ends = found.entry_idx + HORIZON
        assert not ((starts < gap_pos) & (ends >= gap_pos)).any()
        assert found.excluded_warmup_or_gap > HISTORY - 1

    def test_labels_align_with_candidates(self, finder: SymbolCandidateFinder) -> None:
        found = finder.find(make_frame(400), window_start_ms=BASE_MS)
        assert len(found.barriers.labels) == len(found.entry_idx)
        assert np.all(found.tp_distance > found.sl_distance)
