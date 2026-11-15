from collections import Counter

from kavzi_trader.evals.class_metrics_schema import ClassMetricsSchema
from kavzi_trader.evals.joined_case_schema import NO_TRADE, TRADE_SIDES

CLASSES = (*TRADE_SIDES, NO_TRADE)


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


class ConfusionMetrics:
    """3x3 confusion over LONG / SHORT / NO_TRADE from parallel label lists."""

    def __init__(self, actual: list[str], predicted: list[str]) -> None:
        if len(actual) != len(predicted):
            msg = f"actual has {len(actual)} items, predicted has {len(predicted)}"
            raise ValueError(msg)
        unknown = (set(actual) | set(predicted)) - set(CLASSES)
        if unknown:
            msg = f"Unknown classes {sorted(unknown)}; expected {CLASSES}"
            raise ValueError(msg)
        self._counts = Counter(zip(actual, predicted, strict=True))
        self.total = len(actual)

    def count(self, actual: str, predicted: str) -> int:
        return self._counts[(actual, predicted)]

    def per_class(self) -> dict[str, ClassMetricsSchema]:
        result: dict[str, ClassMetricsSchema] = {}
        for name in CLASSES:
            hits = self.count(name, name)
            support = sum(self.count(name, p) for p in CLASSES)
            predicted = sum(self.count(a, name) for a in CLASSES)
            result[name] = ClassMetricsSchema(
                support=support,
                predicted=predicted,
                hits=hits,
                precision=ratio(hits, predicted),
                recall=ratio(hits, support),
                f1=ratio(2 * hits, support + predicted),
            )
        return result

    @property
    def accuracy(self) -> float | None:
        return ratio(sum(self.count(c, c) for c in CLASSES), self.total)

    @property
    def macro_f1(self) -> float | None:
        scores = [m.f1 for m in self.per_class().values() if m.f1 is not None]
        return ratio(sum(scores), len(scores))

    @property
    def trades(self) -> int:
        return sum(self.count(a, side) for a in CLASSES for side in TRADE_SIDES)

    @property
    def trade_hits(self) -> int:
        return sum(self.count(side, side) for side in TRADE_SIDES)

    @property
    def trade_precision(self) -> float | None:
        return ratio(self.trade_hits, self.trades)
