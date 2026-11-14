import logging
from pathlib import Path

from kavzi_trader.evals.eval_case_schema import EvalCaseSchema

logger = logging.getLogger(__name__)


class CaseDatasetFile:
    """JSONL reader/writer: one EvalCaseSchema per line."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def write(self, cases: list[EvalCaseSchema]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = [case.model_dump_json() for case in cases]
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("Wrote %d cases to %s", len(cases), self._path)

    def read(self) -> list[EvalCaseSchema]:
        with self._path.open(encoding="utf-8") as handle:
            return [
                EvalCaseSchema.model_validate_json(line)
                for line in handle
                if line.strip()
            ]
