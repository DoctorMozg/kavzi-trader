from datetime import UTC, date, datetime
from typing import Literal

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.domain.trend_gate_decision import TrendGateDecisionSchema
from kavzi_trader.evals.gate_replay_report import GateReplayReport
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_entry_finder import TrendEntryFinder
from kavzi_trader.evals.trend_entry_schema import TrendEntrySchema
from kavzi_trader.strategies.trend.trend_gate_review_schema import (
    TrendGateReviewSchema,
)
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

DAYS = pd.date_range("2026-06-25", periods=12, freq="D")


class FixedWeights:
    """Replays a given weight matrix as the signal."""

    def __init__(self, weights: np.ndarray) -> None:
        self._weights = weights

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        return self._weights


def _data(closes: list[float]) -> TrendDataSchema:
    frame = pd.DataFrame({"AAAUSDT": closes}, index=DAYS)
    return TrendDataSchema(closes=frame, funding=frame * 0.0)


def _finder(weights: list[float], fee: float = 0.0) -> TrendEntryFinder:
    return TrendEntryFinder(
        FixedWeights(np.array(weights)[:, None]), TurnoverBuffer(0.2), fee
    )


class TestTrendEntryFinder:
    def test_a_position_held_since_warmup_is_not_an_entry(self) -> None:
        # Long from day 0 (warm-up), flat on day 7, long again on day 9.
        weights = [0.1] * 7 + [0.0, 0.0] + [0.1] * 3
        closes = [100.0] * 12

        entries = _finder(weights).entries(
            _data(closes), DAYS[0].date(), date(2026, 7, 1), date(2026, 7, 6)
        )

        assert [e.signal_day for e in entries] == [date(2026, 7, 4)]

    def test_review_time_is_a_minute_after_the_triggering_close(self) -> None:
        weights = [0.0] * 3 + [0.1] * 9

        (entry,) = _finder(weights).entries(
            _data([100.0] * 12), DAYS[0].date(), DAYS[1].date(), DAYS[-1].date()
        )

        assert entry.signal_day == date(2026, 6, 28)
        assert entry.as_of == datetime(2026, 6, 29, 0, 1, tzinfo=UTC)
        assert entry.exit_day is None

    def test_net_pnl_covers_the_holding_period_and_both_fees(self) -> None:
        # Long 0.5 on day 2 (close 100), flat on day 4; days 3 and 4 return +10%, +10%.
        weights = [0.0, 0.0, 0.5, 0.5, 0.0] + [0.0] * 7
        closes = [100.0, 100.0, 100.0, 110.0, 121.0] + [121.0] * 7

        (entry,) = _finder(weights, fee=0.001).entries(
            _data(closes), DAYS[0].date(), DAYS[1].date(), DAYS[-1].date()
        )

        assert entry.exit_day == DAYS[4].date()
        assert entry.net_pnl == pytest.approx(0.5 * 0.1 * 2 - 2 * 0.001 * 0.5)

    def test_rejects_a_window_starting_before_warmup(self) -> None:
        with pytest.raises(ValueError, match="warmup_from < first"):
            _finder([0.0] * 12).entries(
                _data([100.0] * 12), DAYS[3].date(), DAYS[3].date(), DAYS[5].date()
            )


def _entry(symbol: str, pnl: float) -> TrendEntrySchema:
    return TrendEntrySchema(
        symbol=symbol,
        signal_day=date(2026, 7, 3),
        as_of=datetime(2026, 7, 4, 0, 1, tzinfo=UTC),
        weight=0.05,
        exit_day=None,
        net_pnl=pnl,
    )


def _review(symbol: str, decision: Literal["KEEP", "VETO"]) -> TrendGateReviewSchema:
    sample = TrendGateDecisionSchema(
        verdict=decision, catalyst="hack", reasoning="A venue listing it was drained."
    )
    return TrendGateReviewSchema(
        symbol=symbol,
        as_of=datetime(2026, 7, 4, 0, 1, tzinfo=UTC),
        decision=decision,
        samples=[sample] * 3,
        coin_headlines=2,
        other_headlines=5,
        prompt_sha="abc",
    )


class TestGateReplayReport:
    def test_vetoing_a_loser_has_positive_value(self) -> None:
        report = GateReplayReport(
            [_entry("A", -0.01), _entry("B", 0.02)],
            [_review("A", "VETO"), _review("B", "KEEP")],
        )

        assert report.veto_value == pytest.approx(0.01)
        assert report.decision().startswith("CONTINUE")

    def test_vetoing_a_winner_kills_the_gate(self) -> None:
        report = GateReplayReport([_entry("A", 0.02)], [_review("A", "VETO")])

        assert report.decision() == "KILL: vetoed entries made money"

    def test_too_many_vetoes_kill_the_gate(self) -> None:
        symbols = [f"S{i}" for i in range(6)]
        report = GateReplayReport(
            [_entry(s, -0.01) for s in symbols], [_review(s, "VETO") for s in symbols]
        )

        assert report.decision().startswith("KILL: 6 vetoes")

    def test_an_unreviewed_entry_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="no review"):
            GateReplayReport([_entry("A", 0.0)], [])
