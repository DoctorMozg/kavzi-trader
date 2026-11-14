from pathlib import Path

import pytest
from starlette.testclient import TestClient

from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.message_schemas import (
    UI_SERVER_MESSAGE_ADAPTER,
    UiEventMessageSchema,
    UiSnapshotMessageSchema,
)
from kavzi_trader.ui.server.app import UiWebApp
from kavzi_trader.ui.server.broadcaster import UiBroadcaster
from kavzi_trader.ui.server.projection import UiStateProjection
from kavzi_trader.ui.server.stream_service import UiStreamService
from tests.ui.factories import make_account, make_decision, make_trade
from tests.ui.fake_ui_redis import FakeUiRedis

CONFIG = UiConfigSchema(read_block_ms=100)


@pytest.fixture
def redis() -> FakeUiRedis:
    fake = FakeUiRedis()
    fake.add(CONFIG.ticks_stream, make_account())
    fake.add(CONFIG.events_stream, make_decision())
    return fake


@pytest.fixture
def client(redis: FakeUiRedis, tmp_path: Path) -> TestClient:
    (tmp_path / "index.html").write_text("<html>dashboard</html>")
    projection = UiStateProjection(CONFIG)
    broadcaster = UiBroadcaster(queue_size=16)
    app = UiWebApp(
        projection=projection,
        broadcaster=broadcaster,
        stream_service=UiStreamService(redis, CONFIG, projection, broadcaster),  # type: ignore[arg-type]
        static_dir=tmp_path,
    ).build()
    return TestClient(app)


class TestUiWebApp:
    def test_websocket_sends_snapshot_then_deltas(
        self,
        client: TestClient,
        redis: FakeUiRedis,
    ) -> None:
        with client, client.websocket_connect("/ws") as ws:
            snapshot = UI_SERVER_MESSAGE_ADAPTER.validate_json(ws.receive_text())
            redis.add(CONFIG.events_stream, make_trade())
            delta = UI_SERVER_MESSAGE_ADAPTER.validate_json(ws.receive_text())

        assert isinstance(snapshot, UiSnapshotMessageSchema)
        assert snapshot.seq == 2
        assert snapshot.snapshot.account is not None
        assert len(snapshot.snapshot.decisions) == 1
        assert isinstance(delta, UiEventMessageSchema)
        assert delta.seq == snapshot.seq + 1
        assert delta.event.type == "trade"

    def test_snapshot_endpoint_serializes_decimals_as_strings(
        self,
        client: TestClient,
    ) -> None:
        with client:
            body = client.get("/api/snapshot").json()

        assert body["type"] == "snapshot"
        assert body["snapshot"]["account"]["balance_usdt"] == "1050"

    def test_serves_static_index_and_closes_redis(
        self,
        client: TestClient,
        redis: FakeUiRedis,
    ) -> None:
        with client:
            response = client.get("/")

        assert response.status_code == 200
        assert "dashboard" in response.text
        assert redis.closed


def test_missing_static_dir_serves_api_only(redis: FakeUiRedis, tmp_path: Path) -> None:
    projection = UiStateProjection(CONFIG)
    broadcaster = UiBroadcaster(queue_size=16)
    app = UiWebApp(
        projection=projection,
        broadcaster=broadcaster,
        stream_service=UiStreamService(redis, CONFIG, projection, broadcaster),  # type: ignore[arg-type]
        static_dir=tmp_path / "missing",
    ).build()

    with TestClient(app) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/snapshot").status_code == 200
