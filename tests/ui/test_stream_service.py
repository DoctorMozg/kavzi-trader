import asyncio
from decimal import Decimal

import pytest

from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.message_schemas import (
    UI_SERVER_MESSAGE_ADAPTER,
    UiEventMessageSchema,
)
from kavzi_trader.ui.server.broadcaster import UiBroadcaster
from kavzi_trader.ui.server.projection import UiStateProjection
from kavzi_trader.ui.server.stream_service import UiStreamService
from tests.ui.factories import make_account, make_decision, make_trade
from tests.ui.fake_ui_redis import FakeUiRedis

CONFIG = UiConfigSchema(read_block_ms=100)


class _Harness:
    def __init__(self) -> None:
        self.redis = FakeUiRedis()
        self.projection = UiStateProjection(CONFIG)
        self.broadcaster = UiBroadcaster(queue_size=16)
        self.service = UiStreamService(
            self.redis,  # type: ignore[arg-type]
            CONFIG,
            self.projection,
            self.broadcaster,
        )


@pytest.fixture
def harness() -> _Harness:
    return _Harness()


class TestUiStreamService:
    async def test_history_replays_events_and_only_latest_tick(
        self,
        harness: _Harness,
    ) -> None:
        harness.redis.add(CONFIG.events_stream, make_decision())
        harness.redis.add(CONFIG.events_stream, make_trade())
        harness.redis.add(CONFIG.ticks_stream, make_account(balance="1000"))
        harness.redis.add(CONFIG.ticks_stream, make_account(balance="1200"))

        await harness.service.load_history()

        snapshot = harness.projection.snapshot_message().snapshot
        assert len(snapshot.decisions) == 1
        assert len(snapshot.trades) == 1
        assert snapshot.account is not None
        assert snapshot.account.balance_usdt == Decimal(1200)
        assert harness.projection.seq == 3

    async def test_live_events_are_broadcast_with_seq(self, harness: _Harness) -> None:
        harness.redis.add(CONFIG.events_stream, make_decision())
        await harness.service.load_history()
        queue = harness.broadcaster.subscribe()
        task = asyncio.create_task(harness.service.run())
        try:
            harness.redis.add(CONFIG.events_stream, make_trade())
            raw = await asyncio.wait_for(queue.get(), timeout=2)
        finally:
            task.cancel()

        assert raw is not None
        message = UI_SERVER_MESSAGE_ADAPTER.validate_json(raw)
        assert isinstance(message, UiEventMessageSchema)
        assert message.seq == 2
        assert message.event.type == "trade"

    async def test_malformed_entry_is_skipped(
        self,
        harness: _Harness,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        harness.redis.add_raw(CONFIG.events_stream, {"event": '{"type": "bogus"}'})
        harness.redis.add_raw(CONFIG.events_stream, {"other": "x"})
        harness.redis.add(CONFIG.events_stream, make_decision())

        await harness.service.load_history()

        assert harness.projection.seq == 1
        assert caplog.text.count("Skipping malformed UI event") == 2
