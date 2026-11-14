import json
import logging
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from kavzi_trader.commons.time_utility import utc_now

_RESERVED_RECORD_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    },
)


def _json_default(value: object) -> object:
    # Decimal goes out as str so precision survives the round trip.
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return repr(value)


class JsonLogFormatter(logging.Formatter):
    """Formats log records as JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_FIELDS
        }
        if extra.get("taskName") is None:
            extra.pop("taskName", None)
        payload: dict[str, object] = {
            "timestamp": utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "extra": extra,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, default=_json_default)
        except TypeError, ValueError:
            # Non-str dict keys or cycles defeat `default`; a lossy line beats none.
            payload["extra"] = {key: repr(value) for key, value in extra.items()}
            return json.dumps(payload, default=_json_default)
