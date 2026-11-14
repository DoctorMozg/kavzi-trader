from decimal import Decimal

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.event_schemas import UI_EVENT_ADAPTER, UiAccountEventSchema
from kavzi_trader.ui.redis_publisher import EVENT_FIELD, RedisUiPublisher
from tests.ui.factories import make_account, make_decision


class _RecordingRedis:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, str], int]] = []
        self._fail = fail

    async def xadd(
        self,
        name: str,
        fields: dict[str, str],
        maxlen: int,
        approximate: bool,
    ) -> str:
        if self._fail:
            raise RedisConnectionError("redis down")
        assert approximate
        self.calls.append((name, fields, maxlen))
        return "1-0"


@pytest.fixture
def config() -> UiConfigSchema:
    return UiConfigSchema(events_max_len=1000, ticks_max_len=50)


class TestRedisUiPublisher:
    async def test_account_goes_to_ticks_stream(self, config: UiConfigSchema) -> None:
        redis = _RecordingRedis()
        await RedisUiPublisher(redis, config).publish(make_account())  # type: ignore[arg-type]

        assert [(c[0], c[2]) for c in redis.calls] == [("kt:ui:ticks", 50)]

    async def test_other_events_go_to_events_stream(
        self,
        config: UiConfigSchema,
    ) -> None:
        redis = _RecordingRedis()
        await RedisUiPublisher(redis, config).publish(make_decision())  # type: ignore[arg-type]

        assert [(c[0], c[2]) for c in redis.calls] == [("kt:ui:events", 1000)]

    async def test_payload_round_trips_with_exact_decimals(
        self,
        config: UiConfigSchema,
    ) -> None:
        redis = _RecordingRedis()
        await RedisUiPublisher(redis, config).publish(make_account())  # type: ignore[arg-type]

        parsed = UI_EVENT_ADAPTER.validate_json(redis.calls[0][1][EVENT_FIELD])
        assert isinstance(parsed, UiAccountEventSchema)
        assert parsed.unrealized_pnl_usdt == Decimal("12.5")
        assert parsed == make_account()

    async def test_redis_failure_is_logged_not_raised(
        self,
        config: UiConfigSchema,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        publisher = RedisUiPublisher(_RecordingRedis(fail=True), config)  # type: ignore[arg-type]

        await publisher.publish(make_decision())

        assert "Failed to publish UI event decision" in caplog.text


def test_decimals_serialize_as_strings() -> None:
    dumped = make_account().model_dump(mode="json")

    assert dumped["balance_usdt"] == "1050"
    assert dumped["prices"] == {"BTCUSDT": "61250"}
