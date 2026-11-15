from collections import Counter
from collections.abc import Callable

from kavzi_trader.evals.joined_case_schema import JoinedCaseSchema

CONFLUENCE_BUCKETS = ("0-2", "3-4", "5-6", "7-8", "9+")
_BUCKET_WIDTH = 2


def confluence_bucket(score: int) -> str:
    # Buckets 3-4, 5-6, 7-8 are two wide; 0-2 and 9+ absorb the tails.
    index = max(0, min((score - 1) // _BUCKET_WIDTH, len(CONFLUENCE_BUCKETS) - 1))
    return CONFLUENCE_BUCKETS[index]


class StageStats:
    """Per-label counts of what Scout, Analyst and Trader said."""

    def __init__(self, cases: list[JoinedCaseSchema]) -> None:
        self._cases = cases

    def scout_verdicts(self) -> dict[str, Counter[str]]:
        return self._by_label(lambda j: j.result.scout_verdict or "none")

    def analyst_validity(self) -> dict[str, Counter[str]]:
        """valid / invalid per label; no_verdict covers failed or skipped Analysts."""

        def verdict(j: JoinedCaseSchema) -> str | None:
            analyst = j.result.analyst
            if analyst is None or analyst.setup_valid is None:
                return "no_verdict"
            return "valid" if analyst.setup_valid else "invalid"

        return self._by_label(verdict)

    def valid_directions(self) -> dict[str, Counter[str]]:
        """Direction the Analyst chose among its valid setups, per label."""

        def direction(j: JoinedCaseSchema) -> str | None:
            analyst = j.result.analyst
            return (
                (analyst.direction or "none")
                if analyst and analyst.setup_valid
                else None
            )

        return self._by_label(direction)

    def confluence_scores(self) -> dict[str, list[int]]:
        scores: dict[str, list[int]] = {}
        for joined in self._cases:
            analyst = joined.result.analyst
            if analyst is not None and analyst.confluence_score is not None:
                scores.setdefault(joined.case.label.value, []).append(
                    analyst.confluence_score
                )
        return scores

    def validity_vs_trade_label(self) -> Counter[str]:
        """2x2 cells keyed like ``valid/trade``, over cases with an Analyst verdict."""
        cells: Counter[str] = Counter()
        for joined in self._cases:
            analyst = joined.result.analyst
            if analyst is None or analyst.setup_valid is None:
                continue
            valid = "valid" if analyst.setup_valid else "invalid"
            tradeable = "trade" if joined.case.label.value != "NO_TRADE" else "no_trade"
            cells[f"{valid}/{tradeable}"] += 1
        return cells

    def trader_actions(self) -> dict[str, Counter[str]]:
        """Action per label among cases that reached the Trader live."""
        return self._by_label(lambda j: self._action(j, forced=False))

    def forced_trader_actions(self) -> dict[str, Counter[str]]:
        """Action per label among cases whose Trader stage was forced."""
        return self._by_label(lambda j: self._action(j, forced=True))

    @staticmethod
    def _action(joined: JoinedCaseSchema, *, forced: bool) -> str | None:
        trader = joined.result.trader
        if trader is None or joined.result.trader_forced != forced:
            return None
        return trader.action or "no_decision"

    def _by_label(
        self, key: Callable[[JoinedCaseSchema], str | None]
    ) -> dict[str, Counter[str]]:
        grouped: dict[str, Counter[str]] = {}
        for joined in self._cases:
            value = key(joined)
            if value is not None:
                grouped.setdefault(joined.case.label.value, Counter())[value] += 1
        return grouped
