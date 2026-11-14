import numpy as np
import pytest

from kavzi_trader.evals.barrier_enums import BarrierOutcome, CaseLabel
from kavzi_trader.evals.side_outcome_schema import SideOutcomeSchema
from kavzi_trader.evals.triple_barrier import TripleBarrierLabeler

HORIZON = 4
ENTRY = 100.0
SL = 2.0
TP = 4.0


def _label(
    bars: list[tuple[float, float, float]], sl: float = SL
) -> tuple[CaseLabel, SideOutcomeSchema, SideOutcomeSchema]:
    """bars: (high, low, close) for the candles after a close-100 decision."""
    high = np.array([ENTRY] + [b[0] for b in bars])
    low = np.array([ENTRY] + [b[1] for b in bars])
    close = np.array([ENTRY] + [b[2] for b in bars])
    result = TripleBarrierLabeler(HORIZON).label(
        high,
        low,
        close,
        np.array([0], dtype=np.int64),
        np.array([sl]),
        np.array([TP]),
    )
    return result.labels[0], result.long.at(0), result.short.at(0)


def _flat(count: int) -> list[tuple[float, float, float]]:
    return [(101.0, 99.0, 100.0)] * count


class TestTripleBarrierLabeler:
    def test_long_tp_first(self) -> None:
        label, long, short = _label([(101, 99, 100), (104.5, 100, 104), *_flat(2)])
        assert label is CaseLabel.LONG
        assert (long.outcome, long.bars_to_exit) == (BarrierOutcome.TP, 2)
        assert long.r_multiple == pytest.approx(TP / SL)
        assert short.outcome is BarrierOutcome.SL
        assert short.bars_to_exit == 2
        assert short.r_multiple == -1.0

    def test_short_tp_first(self) -> None:
        label, long, short = _label([(100.5, 95.5, 96), *_flat(3)])
        assert label is CaseLabel.SHORT
        assert (short.outcome, short.bars_to_exit) == (BarrierOutcome.TP, 1)
        assert short.r_multiple == pytest.approx(2.0)
        assert long.outcome is BarrierOutcome.SL
        assert long.r_multiple == -1.0

    def test_both_sides_stop_out_is_no_trade(self) -> None:
        label, long, short = _label([(103, 97, 100), *_flat(3)])
        assert label is CaseLabel.NO_TRADE
        assert long.outcome is BarrierOutcome.SL
        assert short.outcome is BarrierOutcome.SL
        assert long.bars_to_exit == short.bars_to_exit == 1

    def test_timeout_is_no_trade_with_mark_to_market_r(self) -> None:
        bars = [
            (101, 99, 100),
            (101, 99, 100),
            (101.5, 99.5, 100.5),
            (101.5, 99.5, 101),
        ]
        label, long, short = _label(bars)
        assert label is CaseLabel.NO_TRADE
        assert long.outcome is BarrierOutcome.TIMEOUT
        assert long.bars_to_exit == HORIZON
        assert long.r_multiple == pytest.approx(0.5)
        assert short.outcome is BarrierOutcome.TIMEOUT
        assert short.r_multiple == pytest.approx(-0.5)

    def test_same_bar_sl_and_tp_counts_as_sl(self) -> None:
        # The bar spans both the long TP (104) and long SL (98).
        label, long, _ = _label([(104.5, 97.5, 100), *_flat(3)])
        assert long.outcome is BarrierOutcome.SL
        assert long.r_multiple == -1.0
        assert label is CaseLabel.NO_TRADE

    def test_both_win_labels_by_earliest_tp(self) -> None:
        # Wide stops (6) let both TPs (4) trigger: short on bar 1, long on bar 2.
        bars = [(101.5, 95.5, 98), (104.5, 99, 104), *_flat(2)]
        label, long, short = _label(bars, sl=6.0)
        assert (long.outcome, long.bars_to_exit) == (BarrierOutcome.TP, 2)
        assert (short.outcome, short.bars_to_exit) == (BarrierOutcome.TP, 1)
        assert label is CaseLabel.SHORT

    def test_both_win_in_same_bar_is_no_trade(self) -> None:
        label, long, short = _label([(104.5, 95.5, 100), *_flat(3)], sl=6.0)
        assert long.outcome is short.outcome is BarrierOutcome.TP
        assert long.bars_to_exit == short.bars_to_exit == 1
        assert label is CaseLabel.NO_TRADE

    def test_rejects_entry_without_full_horizon(self) -> None:
        labeler = TripleBarrierLabeler(HORIZON)
        flat = np.full(HORIZON + 1, ENTRY)
        with pytest.raises(ValueError, match="exceeds"):
            labeler.label(
                flat,
                flat,
                flat,
                np.array([1], dtype=np.int64),
                np.array([1.0]),
                np.array([2.0]),
            )
