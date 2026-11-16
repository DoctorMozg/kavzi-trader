import logging
from pathlib import Path

from kavzi_trader.evals.validation.trial_schema import TrialSchema

logger = logging.getLogger(__name__)


class TrialRegistry:
    """Append-only JSONL of every backtested variant, for DSR and PBO."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def record(self, trial: TrialSchema) -> bool:
        """Adds the trial; a rerun of a variant over the same days is not new."""
        if any(t.key == trial.key for t in self.trials(trial.family)):
            logger.debug("Trial %s already registered", trial.key)
            return False
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as registry:
            registry.write(trial.model_dump_json() + "\n")
        logger.info("Registered trial %s", trial.key)
        return True

    def trials(self, family: str) -> list[TrialSchema]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        loaded = [TrialSchema.model_validate_json(line) for line in lines if line]
        return [t for t in loaded if t.family == family]
