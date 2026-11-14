import logging
from typing import cast

from redis.typing import EncodableT, FieldT

from kavzi_trader.events.aggregate_type import UnknownAggregateTypeError
from kavzi_trader.events.config import EventStoreConfigSchema
from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.serialization import (
    SerializedEventDict,
    deserialize_event,
    serialize_event,
)
from kavzi_trader.infra.redis_client import RedisStateClient

logger = logging.getLogger(__name__)


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
        stream = self._stream_for_event(event)
        fields = serialize_event(event)
        event_id = await self._redis.client.xadd(
            stream,
            cast("dict[FieldT, EncodableT]", fields),
            maxlen=self._config.stream_max_length,
            approximate=True,
        )
        logger.info(
            "Event stored",
            extra={"event": event.model_dump(mode="json")},
        )
        logger.debug("Appended event %s to %s", event_id, stream)
        return str(event_id)

    async def read(
        self,
        stream: str,
        start: str = "-",
        end: str = "+",
        count: int | None = None,
    ) -> list[EventSchema]:
        entries = await self._redis.client.xrange(stream, start, end, count=count)
        # decode_responses=True: redis returns str ids and fields at runtime.
        return [
            deserialize_event(cast("SerializedEventDict", fields))
            for _, fields in entries or []
        ]

    def _stream_for_event(self, event: EventSchema) -> str:
        stream = self._config.streams.get(event.aggregate_type)
        if stream is None:
            logger.error(
                "No stream configured for aggregate type %s",
                event.aggregate_type,
                extra={"event_id": event.event_id},
            )
            msg = f"No stream configured for aggregate type {event.aggregate_type!r}"
            raise UnknownAggregateTypeError(msg)
        return stream
