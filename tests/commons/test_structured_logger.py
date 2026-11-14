import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from kavzi_trader.commons.structured_logger import JsonLogFormatter


def test_json_log_formatter() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert payload["message"] == "hello"


def _format(**extra: object) -> dict[str, object]:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    payload: dict[str, object] = json.loads(JsonLogFormatter().format(record))
    return payload


class _Colour(Enum):
    RED = "red"


class _Row(BaseModel):
    price: Decimal


def test_extra_values_of_rich_types_are_serialized() -> None:
    payload = _format(
        price=Decimal("0.1000000000000000055"),
        at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        colour=_Colour.RED,
        row=_Row(price=Decimal("1.5")),
    )

    assert payload["extra"] == {
        "price": "0.1000000000000000055",
        "at": "2026-01-02T03:04:05+00:00",
        "colour": "red",
        "row": {"price": "1.5"},
    }


def test_unserializable_extra_falls_back_to_repr_instead_of_dropping_line() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    payload = _format(thing=Opaque(), mapping={(1, 2): "x"})

    assert payload["message"] == "hello"
    assert payload["extra"] == {"thing": "<opaque>", "mapping": "{(1, 2): 'x'}"}


def test_task_name_is_omitted_when_none() -> None:
    payload = _format(taskName=None)

    assert payload["extra"] == {}
