import logging
from collections.abc import Iterator

import pytest

from kavzi_trader.cli.commands.ui import route_uvicorn_logs


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def project_handler() -> Iterator[_Collect]:
    project, server = (
        logging.getLogger("kavzi_trader"),
        logging.getLogger("uvicorn.error"),
    )
    saved = (project.handlers[:], server.handlers[:], server.level, server.propagate)
    handler = _Collect()
    project.handlers = [handler]
    yield handler
    project.handlers, server.handlers = saved[0], saved[1]
    server.setLevel(saved[2])
    server.propagate = saved[3]


class TestRouteUvicornLogs:
    def test_server_lines_reach_the_project_handlers(
        self, project_handler: _Collect
    ) -> None:
        route_uvicorn_logs()

        logging.getLogger("uvicorn.error").info("Shutting down")

        assert project_handler.messages == ["Shutting down"]
