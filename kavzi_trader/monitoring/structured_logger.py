import json
import logging

from kavzi_trader.commons.time_utility import utc_now


class JsonLogFormatter(logging.Formatter):
    """Formats log records as JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)
