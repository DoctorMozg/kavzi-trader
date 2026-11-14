import logging
from pathlib import Path

from pydantic import ValidationError

from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.run_header_schema import RunHeaderSchema

logger = logging.getLogger(__name__)


class ResultStore:
    """Append-only JSONL of case results plus a sidecar with the run header."""

    def __init__(self, results_dir: Path, run_id: str) -> None:
        self._results = results_dir / f"{run_id}.jsonl"
        self._header = results_dir / f"{run_id}.header.json"

    @property
    def results_path(self) -> Path:
        return self._results

    def write_header(self, header: RunHeaderSchema) -> None:
        self._header.parent.mkdir(parents=True, exist_ok=True)
        self._header.write_text(header.model_dump_json(indent=2), encoding="utf-8")

    def read_header(self) -> RunHeaderSchema:
        if not self._header.exists():
            msg = f"No run header at {self._header}; cannot resume that run"
            raise FileNotFoundError(msg)
        return RunHeaderSchema.model_validate_json(
            self._header.read_text(encoding="utf-8")
        )

    def append(self, result: CaseResultSchema) -> None:
        self._results.parent.mkdir(parents=True, exist_ok=True)
        with self._results.open("a", encoding="utf-8") as handle:
            handle.write(result.model_dump_json() + "\n")

    def read_all(self) -> list[CaseResultSchema]:
        if not self._results.exists():
            return []
        results: list[CaseResultSchema] = []
        with self._results.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    results.append(CaseResultSchema.model_validate_json(line))
                except ValidationError:
                    # A crash mid-write leaves one torn line; that case reruns.
                    logger.warning(
                        "Skipping unreadable line %d of %s", number, self._results
                    )
        return results

    def completed_ids(self) -> set[str]:
        """Cases that finished; errored ones are not done and run again."""
        return {r.case_id for r in self.read_all() if r.status == "ok"}
