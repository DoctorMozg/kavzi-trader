import logging
from pathlib import Path

from kavzi_trader.evals.case_dataset_file import CaseDatasetFile
from kavzi_trader.evals.joined_case_schema import JoinedCaseSchema
from kavzi_trader.evals.loaded_run_schema import LoadedRunSchema
from kavzi_trader.evals.result_store import ResultStore

logger = logging.getLogger(__name__)


class RunLoader:
    """Reads a run, its header and its dataset, joined on case_id."""

    def __init__(self, results_dir: Path) -> None:
        self._results_dir = results_dir

    def load(self, run_id: str) -> LoadedRunSchema:
        store = ResultStore(self._results_dir, run_id)
        header = store.read_header()
        if not store.results_path.exists():
            msg = f"No results at {store.results_path}"
            raise FileNotFoundError(msg)
        # A resumed run holds an error line before the retry; the last line wins.
        latest = {r.case_id: r for r in store.read_all()}
        cases = {c.case_id: c for c in CaseDatasetFile(Path(header.dataset)).read()}
        unknown = sorted(set(latest) - set(cases))
        if unknown:
            msg = f"Run {run_id} has cases missing from {header.dataset}: {unknown[:3]}"
            raise ValueError(msg)
        scored = [
            JoinedCaseSchema(result=r, case=cases[r.case_id])
            for r in latest.values()
            if r.status == "ok"
        ]
        logger.info("Loaded %d results (%d scored)", len(latest), len(scored))
        return LoadedRunSchema(
            header=header, results=list(latest.values()), scored=scored
        )
