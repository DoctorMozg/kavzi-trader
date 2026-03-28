import logging
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.events.config import EventStoreConfigSchema
from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.serialization import deserialize_event, serialize_event
from kavzi_trader.spine.state.redis_client import RedisStateClient

logger = logging.getLogger(__name__)


class _EventEntry(BaseModel):
    stream_id: str
    event: EventSchema
    model_config = ConfigDict(frozen=True)


class RedisEventStore:
    """Redis Streams-backed event store."""

    def __init__(
        self,
        redis_client: RedisStateClient,
        config: EventStoreConfigSchema,
    ) -> None:
        self._redis = redis_client
        self._config = config

    async def append(self, event: EventSchema) -> str:
        try:
            stream = self._stream_for_event(event)
            fields = serialize_event(event)
            event_id = await self._redis.client.xadd(
                stream,
                fields,
                maxlen=self._config.stream_max_length,
                approximate=True,
            )
            logger.info(
                "Event stored",
                extra={"event": event.model_dump(mode="json")},
            )
            logger.debug("Appended event %s to %s", event_id, stream)
            return str(event_id)
        except Exception:
            logger.exception(
                "Failed to append event %s to store",
                event.event_id,
            )
            return ""

    async def read(
        self,
        stream: str,
        start: str = "-",
        end: str = "+",
        count: int | None = None,
    ) -> list[EventSchema]:
        entries = await self._read_entries(stream, start, end, count)
        return [entry.event for entry in entries]

    async def query(
        self,
        stream: str,
        after: datetime | None = None,
        symbol: str | None = None,
        count: int | None = None,
    ) -> list[EventSchema]:
        events = await self.read(stream, count=count)
        filtered = []
        for event in events:
            if after and event.timestamp < after:
                continue
            if symbol and event.data.get("symbol") != symbol:
                continue
            filtered.append(event)
        return filtered

    async def trim_expired(self) -> None:
        cutoff = utc_now() - timedelta(days=self._config.retention_days)
        for stream in self._config.streams.values():
            await self._trim_stream(stream, cutoff)

    async def _trim_stream(self, stream: str, cutoff: datetime) -> None:
        entries = await self._read_entries(stream)
        for entry in entries:
            if entry.event.timestamp < cutoff:
                await self._redis.client.xdel(stream, entry.stream_id)

    def _stream_for_event(self, event: EventSchema) -> str:
        return self._config.streams.get(event.aggregate_type, event.aggregate_type)

    async def _read_entries(
        self,
        stream: str,
        start: str = "-",
        end: str = "+",
        count: int | None = None,
    ) -> list[_EventEntry]:
        entries = await self._redis.client.xrange(stream, start, end, count=count)
        return [
            _EventEntry(
                stream_id=entry[0],
                event=deserialize_event(entry[1]),
            )
            for entry in entries
        ]
