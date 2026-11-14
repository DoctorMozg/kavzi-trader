import asyncio
import logging
from typing import cast

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.typing import KeyT, StreamIdT

from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.event_schemas import UI_EVENT_ADAPTER
from kavzi_trader.ui.message_schemas import UiEventMessageSchema
from kavzi_trader.ui.redis_publisher import EVENT_FIELD
from kavzi_trader.ui.server.broadcaster import UiBroadcaster
from kavzi_trader.ui.server.projection import UiStateProjection

logger = logging.getLogger(__name__)

_READ_BATCH = 500
_RECONNECT_DELAY_S = 2.0

# Shapes returned with decode_responses=True and the default (RESP2-style) parser.
type StreamEntry = tuple[str, dict[str, str]]
type StreamBatch = list[tuple[str, list[StreamEntry]]]


class UiStreamService:
    """Replays the UI streams into the projection, then tails them live."""

    def __init__(
        self,
        redis: Redis,
        config: UiConfigSchema,
        projection: UiStateProjection,
        broadcaster: UiBroadcaster,
    ) -> None:
        self._redis = redis
        self._config = config
        self._projection = projection
        self._broadcaster = broadcaster
        self._last_ids: dict[KeyT, StreamIdT] = {
            config.events_stream: "0-0",
            config.ticks_stream: "0-0",
        }

    async def load_history(self) -> None:
        events = cast(
            "list[StreamEntry]",
            await self._redis.xrange(self._config.events_stream),
        )
        # Only the newest tick matters: each one is a full account state.
        ticks = cast(
            "list[StreamEntry]",
            await self._redis.xrevrange(self._config.ticks_stream, count=1),
        )
        self._ingest(self._config.events_stream, events)
        self._ingest(self._config.ticks_stream, ticks)
        logger.info(
            "Loaded UI history: events=%d ticks=%d seq=%d",
            len(events),
            len(ticks),
            self._projection.seq,
        )

    async def run(self) -> None:
        logger.info("UI stream tail started, streams=%s", list(self._last_ids))
        while True:
            try:
                response = cast(
                    "StreamBatch",
                    await self._redis.xread(
                        dict(self._last_ids),
                        count=_READ_BATCH,
                        block=self._config.read_block_ms,
                    ),
                )
            except RedisConnectionError, RedisTimeoutError:
                logger.warning(
                    "UI stream read failed, retrying in %.1fs",
                    _RECONNECT_DELAY_S,
                    exc_info=True,
                )
                await asyncio.sleep(_RECONNECT_DELAY_S)
                continue
            for stream, entries in response:
                self._ingest(stream, entries)

    async def close(self) -> None:
        await self._redis.aclose()

    def _ingest(self, stream: str, entries: list[StreamEntry]) -> None:
        for entry_id, fields in entries:
            # Advance before parsing so a malformed entry is skipped, not retried.
            self._last_ids[stream] = entry_id
            try:
                event = UI_EVENT_ADAPTER.validate_json(fields[EVENT_FIELD])
            except KeyError, ValidationError:
                logger.exception(
                    "Skipping malformed UI event %s in %s",
                    entry_id,
                    stream,
                    extra={"stream": stream, "entry_id": entry_id},
                )
                continue
            seq = self._projection.apply(event)
            if self._broadcaster.client_count:
                message = UiEventMessageSchema(seq=seq, event=event)
                self._broadcaster.broadcast(message.model_dump_json())
