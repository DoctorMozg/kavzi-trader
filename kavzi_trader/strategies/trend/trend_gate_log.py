from pathlib import Path

from kavzi_trader.strategies.trend.trend_gate_review_schema import (
    TrendGateReviewSchema,
)


class TrendGateLog:
    """Append-only JSONL of gate reviews, the input of the preregistered scoring."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, review: TrendGateReviewSchema) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as out:
            out.write(review.model_dump_json() + "\n")

    def read(self) -> list[TrendGateReviewSchema]:
        if not self._path.exists():
            return []
        return [
            TrendGateReviewSchema.model_validate_json(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
