import logging
import math

import numpy as np
import pandas as pd

from kavzi_trader.evals.barrier_enums import CaseLabel, OutcomeCode
from kavzi_trader.evals.signal_bracket_schema import SignalBracketSchema
from kavzi_trader.evals.signal_edge_schema import (
    BracketEdgeSchema,
    EdgeStatSchema,
    ScoreBucketSchema,
    SignalEdgeSchema,
)
from kavzi_trader.evals.signal_sampler import SIDES
from kavzi_trader.evals.triple_barrier import TripleBarrierLabeler

logger = logging.getLogger(__name__)

_Z95 = 1.96
_TOP_SCORE_BUCKET = 4


class SignalEdgeAnalyzer:
    """Labels sampled bars with a bracket and measures each signal's R edge."""

    def __init__(self, stride: int, signals: tuple[str, ...]) -> None:
        self._stride = stride
        self._signals = signals

    def analyze(
        self,
        samples: pd.DataFrame,
        frames: dict[str, pd.DataFrame],
        bracket: SignalBracketSchema,
    ) -> BracketEdgeSchema:
        outcomes = self._label(samples, frames, bracket)
        # Bars `stride` apart share most of a `horizon`-bar outcome window, so
        # the naive interval is too narrow by about sqrt(horizon / stride).
        widening = math.sqrt(max(1.0, bracket.horizon_bars / self._stride))
        signals: list[SignalEdgeSchema] = []
        buckets: list[ScoreBucketSchema] = []
        base: dict[str, EdgeStatSchema] = {}
        for side in SIDES:
            r = outcomes[f"{side}_r"].to_numpy()
            win = outcomes[f"{side}_win"].to_numpy()
            base[side] = self._stat(r, win, widening)
            for name in self._signals:
                fired = samples[f"{side}_{name}"].to_numpy(dtype=bool)
                signals.append(
                    SignalEdgeSchema(
                        side=side,
                        signal=name,
                        fired_share=float(fired.mean()) if len(fired) else 0.0,
                        fired=self._stat(r[fired], win[fired], widening),
                        not_fired=self._stat(r[~fired], win[~fired], widening),
                    )
                )
            score = samples[f"{side}_score"].to_numpy().clip(max=_TOP_SCORE_BUCKET)
            for value in range(_TOP_SCORE_BUCKET + 1):
                mask = score == value
                label = f"{value}+" if value == _TOP_SCORE_BUCKET else str(value)
                buckets.append(
                    ScoreBucketSchema(
                        side=side,
                        bucket=label,
                        stat=self._stat(r[mask], win[mask], widening),
                    )
                )
        shares = outcomes["label"].value_counts(normalize=True)
        logger.info("Analyzed %d bars under %s", len(samples), bracket.label)
        return BracketEdgeSchema(
            bracket=bracket,
            samples=len(samples),
            ci_widening=widening,
            label_shares={
                label.value: float(shares.get(label.value, 0.0)) for label in CaseLabel
            },
            base=base,
            signals=signals,
            score_buckets=buckets,
        )

    @staticmethod
    def _label(
        samples: pd.DataFrame,
        frames: dict[str, pd.DataFrame],
        bracket: SignalBracketSchema,
    ) -> pd.DataFrame:
        labeler = TripleBarrierLabeler(bracket.horizon_bars)
        parts = []
        for symbol, group in samples.groupby("symbol", sort=False):
            frame = frames[str(symbol)]
            atr = group["atr"].to_numpy(dtype=np.float64)
            barriers = labeler.label(
                frame["high"].to_numpy(dtype=np.float64),
                frame["low"].to_numpy(dtype=np.float64),
                frame["close"].to_numpy(dtype=np.float64),
                group["idx"].to_numpy(dtype=np.int64),
                atr * bracket.sl_atr,
                atr * bracket.tp_atr,
            )
            parts.append(
                pd.DataFrame(
                    {
                        "label": [label.value for label in barriers.labels],
                        "LONG_r": barriers.long.r_multiple,
                        "SHORT_r": barriers.short.r_multiple,
                        "LONG_win": barriers.long.outcome_code == OutcomeCode.TP,
                        "SHORT_win": barriers.short.outcome_code == OutcomeCode.TP,
                    },
                    index=group.index,
                )
            )
        return pd.concat(parts).loc[samples.index]

    @staticmethod
    def _stat(r: np.ndarray, win: np.ndarray, widening: float) -> EdgeStatSchema:
        n = len(r)
        if n == 0:
            return EdgeStatSchema(n=0, mean_r=None, ci95=None, win_rate=None)
        ci = None
        if n > 1:
            ci = float(_Z95 * widening * r.std(ddof=1) / math.sqrt(n))
        return EdgeStatSchema(
            n=n, mean_r=float(r.mean()), ci95=ci, win_rate=float(win.mean())
        )
