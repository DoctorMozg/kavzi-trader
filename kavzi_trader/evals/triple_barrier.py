"""Triple-barrier labels (Lopez de Prado, AFML ch. 3): https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy/
A bar that touches both SL and TP counts as SL; full rules are in evals/README.md.
"""

import logging
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.evals.barrier_enums import BarrierOutcome, CaseLabel, OutcomeCode
from kavzi_trader.evals.side_outcome_schema import SideOutcomeSchema

logger = logging.getLogger(__name__)

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

_OUTCOME_BY_CODE = {
    OutcomeCode.TP: BarrierOutcome.TP,
    OutcomeCode.SL: BarrierOutcome.SL,
    OutcomeCode.TIMEOUT: BarrierOutcome.TIMEOUT,
}


class SideWalkSchema(BaseModel):
    """Per-candidate arrays for one side of the bracket."""

    outcome_code: Annotated[NDArray[np.int8], Field(...)]
    bars_to_exit: Annotated[IntArray, Field(...)]
    r_multiple: Annotated[FloatArray, Field(...)]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    def at(self, position: int) -> SideOutcomeSchema:
        return SideOutcomeSchema(
            outcome=_OUTCOME_BY_CODE[OutcomeCode(int(self.outcome_code[position]))],
            bars_to_exit=int(self.bars_to_exit[position]),
            r_multiple=float(self.r_multiple[position]),
        )


class LabeledBarriersSchema(BaseModel):
    """Case labels plus both sides' walks, aligned with the candidate indices."""

    labels: Annotated[list[CaseLabel], Field(...)]
    long: Annotated[SideWalkSchema, Field(...)]
    short: Annotated[SideWalkSchema, Field(...)]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class TripleBarrierLabeler:
    def __init__(self, horizon_bars: int) -> None:
        if horizon_bars < 1:
            msg = f"horizon_bars must be >= 1, got {horizon_bars}"
            raise ValueError(msg)
        self._horizon = horizon_bars

    def label(
        self,
        high: FloatArray,
        low: FloatArray,
        close: FloatArray,
        entry_idx: IntArray,
        sl_distance: FloatArray,
        tp_distance: FloatArray,
    ) -> LabeledBarriersSchema:
        """Label every candidate; ``entry_idx + horizon_bars`` must be in range."""
        long = self.walk_side(+1, high, low, close, entry_idx, sl_distance, tp_distance)
        short = self.walk_side(
            -1, high, low, close, entry_idx, sl_distance, tp_distance
        )
        labels = self._combine(long, short)
        logger.debug("Labeled %d candidates", len(entry_idx))
        return LabeledBarriersSchema(labels=labels, long=long, short=short)

    def walk_side(
        self,
        sign: Literal[1, -1],
        high: FloatArray,
        low: FloatArray,
        close: FloatArray,
        entry_idx: IntArray,
        sl_distance: FloatArray,
        tp_distance: FloatArray,
        entry: FloatArray | None = None,
    ) -> SideWalkSchema:
        """Walk one side; ``entry`` overrides the decision close as the fill price."""
        if len(entry_idx) and int(entry_idx.max()) + self._horizon >= len(close):
            msg = (
                f"entry index {int(entry_idx.max())} + horizon {self._horizon} "
                f"exceeds {len(close)} candles"
            )
            raise ValueError(msg)
        if entry is None:
            entry = close[entry_idx]
        take_profit = entry + sign * tp_distance
        stop_loss = entry - sign * sl_distance
        count = len(entry_idx)
        outcome = np.full(count, OutcomeCode.TIMEOUT, dtype=np.int8)
        bars = np.full(count, self._horizon, dtype=np.int64)
        unresolved = np.ones(count, dtype=bool)

        for step in range(1, self._horizon + 1):
            bar_high = high[entry_idx + step]
            bar_low = low[entry_idx + step]
            if sign > 0:
                hit_tp = bar_high >= take_profit
                hit_sl = bar_low <= stop_loss
            else:
                hit_tp = bar_low <= take_profit
                hit_sl = bar_high >= stop_loss
            new_sl = unresolved & hit_sl
            new_tp = unresolved & hit_tp & ~hit_sl
            outcome[new_sl] = OutcomeCode.SL
            outcome[new_tp] = OutcomeCode.TP
            bars[new_sl | new_tp] = step
            unresolved &= ~(new_sl | new_tp)
            if not unresolved.any():
                break

        timeout_r = sign * (close[entry_idx + self._horizon] - entry) / sl_distance
        r_multiple = np.select(
            [outcome == OutcomeCode.TP, outcome == OutcomeCode.SL],
            [tp_distance / sl_distance, -1.0],
            default=timeout_r,
        )
        return SideWalkSchema(
            outcome_code=outcome, bars_to_exit=bars, r_multiple=r_multiple
        )

    @staticmethod
    def _combine(long: SideWalkSchema, short: SideWalkSchema) -> list[CaseLabel]:
        long_wins = long.outcome_code == OutcomeCode.TP
        short_wins = short.outcome_code == OutcomeCode.TP
        long_first = long_wins & (
            ~short_wins | (long.bars_to_exit < short.bars_to_exit)
        )
        short_first = short_wins & (
            ~long_wins | (short.bars_to_exit < long.bars_to_exit)
        )
        return [
            CaseLabel.LONG if lf else CaseLabel.SHORT if sf else CaseLabel.NO_TRADE
            for lf, sf in zip(long_first, short_first, strict=True)
        ]
