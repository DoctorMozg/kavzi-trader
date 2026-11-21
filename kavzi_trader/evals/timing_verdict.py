from typing import Literal

from kavzi_trader.evals.bar_quality_schema import BarQualitySchema
from kavzi_trader.evals.timing_arm_schema import TIMING_ARMS
from kavzi_trader.evals.validation.paired_sharpe_schema import PairedSharpeSchema

# Family-wise two-sided error rate shared by the six arms (Bonferroni).
FAMILY_ALPHA = 0.10
# Base Sharpe on each universe from the 2026-11-19 ablation reports.
REPRODUCED = {"fresh": 0.688, "trading": 0.905}
REPRODUCTION_TOLERANCE = 0.002
# Share of listed symbol-days whose 1h-derived close may disagree with the daily bar.
MAX_MISMATCH_SHARE = 0.001


class TimingVerdict:
    """Maps the timing scores to the preregistered per-universe criteria."""

    def __init__(self, n_arms: int = len(TIMING_ARMS)) -> None:
        if n_arms < 1:
            msg = f"need at least one arm, got {n_arms}"
            raise ValueError(msg)
        self._n_arms = n_arms

    @property
    def adjusted_confidence(self) -> float:
        """Per-arm two-sided level: 1 - 0.10 / 6, about 98.33%."""
        return 1.0 - FAMILY_ALPHA / self._n_arms

    @staticmethod
    def fresh_passes(adjusted: PairedSharpeSchema) -> bool:
        """Fresh 115: the Bonferroni-adjusted lower bound must clear zero."""
        return adjusted.lower > 0

    @staticmethod
    def trading_passes(paired: PairedSharpeSchema) -> bool:
        """Trading 8: the Sharpe difference must not be negative."""
        return paired.difference >= 0

    @staticmethod
    def holdout_outcome(
        paired: PairedSharpeSchema,
    ) -> Literal["confirm", "inconclusive", "fail"]:
        """Holdout 8: the 90% lower bound must clear zero to confirm."""
        if paired.lower > 0:
            return "confirm"
        return "inconclusive" if paired.difference > 0 else "fail"

    @staticmethod
    def reproduction_error(universe: str, base_sharpe: float | None) -> str | None:
        # The holdout has no earlier mid-exit score to reproduce.
        expected = REPRODUCED.get(universe)
        if expected is None:
            return None
        if base_sharpe is None or abs(base_sharpe - expected) > REPRODUCTION_TOLERANCE:
            return f"base Sharpe {base_sharpe}, 2026-11-19 reports gave {expected}"
        return None

    @staticmethod
    def quality_error(quality: list[BarQualitySchema]) -> str | None:
        worst = max(quality, key=lambda q: q.mismatch_share)
        if worst.mismatch_share > MAX_MISMATCH_SHARE:
            return (
                f"{worst.day_end_mismatches}/{worst.listed_days} day closes of the "
                f"{worst.hours}h bars differ from the daily bars"
            )
        return None
