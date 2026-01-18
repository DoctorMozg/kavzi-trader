import json
from pathlib import Path

import aiofiles

from kavzi_trader.monitoring.decision_log_schema import DecisionLogSchema


class DecisionLogWriter:
    """Appends decision logs to a JSONL file."""

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path

    async def write(self, entry: DecisionLogSchema) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._log_path, "a", encoding="utf-8") as handle:
            await handle.write(json.dumps(entry.model_dump(mode="json")) + "\n")
