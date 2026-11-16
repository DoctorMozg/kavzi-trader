import hashlib
import json
import logging
from pathlib import Path

from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.settings import ModelSettings

logger = logging.getLogger(__name__)

_PARAMS = TypeAdapter(ModelRequestParameters)
# Per-run bookkeeping pydantic-ai stamps on messages; it never reaches the model.
_VOLATILE_KEYS = frozenset({"timestamp", "run_id", "conversation_id"})


class LlmTape:
    """Append-only JSONL of model responses keyed by a hash of the request."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._responses: dict[str, ModelResponse] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                [response] = ModelMessagesTypeAdapter.validate_python(
                    [entry["response"]]
                )
                if not isinstance(response, ModelResponse):
                    msg = f"{path}: entry {entry['key']} is not a model response"
                    raise TypeError(msg)
                self._responses[entry["key"]] = response
        logger.info("LLM tape %s: %d responses", path, len(self._responses))

    def __len__(self) -> int:
        return len(self._responses)

    def get(self, key: str) -> ModelResponse | None:
        return self._responses.get(key)

    def put(self, key: str, response: ModelResponse) -> None:
        [dumped] = ModelMessagesTypeAdapter.dump_python([response], mode="json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as tape:
            tape.write(json.dumps({"key": key, "response": dumped}) + "\n")
        self._responses[key] = response

    @staticmethod
    def key(
        model_name: str,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        params: ModelRequestParameters,
    ) -> str:
        """Hash of everything the provider would see for this request."""
        payload = {
            "model": model_name,
            "messages": _stable(
                ModelMessagesTypeAdapter.dump_python(messages, mode="json")
            ),
            "settings": model_settings,
            "params": _PARAMS.dump_python(params, mode="json"),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()


def _stable(value: object) -> object:
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_stable(v) for v in value]
    return value
