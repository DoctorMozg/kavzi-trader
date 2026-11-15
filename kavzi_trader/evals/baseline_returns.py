import random

from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.r_stats_schema import RStatsSchema

RANDOM_SEED = 42


class BaselineReturns:
    """R of trivial strategies over the dataset's per-side outcomes, fees ignored."""

    def __init__(self, cases: list[EvalCaseSchema]) -> None:
        self._cases = cases

    def oracle(self) -> RStatsSchema:
        picks = [
            c.long.r_multiple if c.label == "LONG" else c.short.r_multiple
            for c in self._cases
            if c.label != "NO_TRADE"
        ]
        return RStatsSchema.from_r(picks)

    def always_long(self) -> RStatsSchema:
        return RStatsSchema.from_r([c.long.r_multiple for c in self._cases])

    def always_short(self) -> RStatsSchema:
        return RStatsSchema.from_r([c.short.r_multiple for c in self._cases])

    def random_side(self) -> RStatsSchema:
        rng = random.Random(RANDOM_SEED)
        return RStatsSchema.from_r(
            [rng.choice((c.long, c.short)).r_multiple for c in self._cases]
        )

    def random_side_expected(self) -> RStatsSchema:
        """Both sides averaged per case: the mean of a coin flip, without the noise."""
        halves = [(c.long.r_multiple + c.short.r_multiple) / 2 for c in self._cases]
        return RStatsSchema.from_r(halves)
