import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.event_schemas import UiAccountEventSchema, UiEvent

logger = logging.getLogger(__name__)

EVENT_FIELD = "event"


class RedisUiPublisher:
    """Appends dashboard events to bounded Redis streams."""

    def __init__(self, redis: Redis, config: UiConfigSchema) -> None:
        self._redis = redis
        self._config = config

    async def publish(self, event: UiEvent) -> None:
        if isinstance(event, UiAccountEventSchema):
            stream, max_len = self._config.ticks_stream, self._config.ticks_max_len
        else:
            stream, max_len = self._config.events_stream, self._config.events_max_len
        try:
            await self._redis.xadd(
                stream,
                {EVENT_FIELD: event.model_dump_json()},
                maxlen=max_len,
                approximate=True,
            )
        except RedisError:
            # The dashboard is observability only; a Redis hiccup must not
            # interrupt order handling in the caller.
            logger.exception(
                "Failed to publish UI event %s to %s",
                event.type,
                stream,
                extra={"event_type": event.type, "stream": stream},
            )
