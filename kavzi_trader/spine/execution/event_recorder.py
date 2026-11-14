import logging
from uuid import uuid4

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.events.store import RedisEventStore

logger = logging.getLogger(__name__)


class ExecutionEventRecorder:
    """Writes audit events without letting a store failure break trading."""

    def __init__(self, event_store: RedisEventStore | None) -> None:
        self._event_store = event_store

    async def record(
        self,
        aggregate_id: str,
        aggregate_type: AggregateType,
        event_type: str,
        data: dict[str, str | int | float | None],
    ) -> None:
        if self._event_store is None:
            return
        event = EventSchema(
            event_id=str(uuid4()),
            event_type=event_type,
            version=1,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            data=data,
            metadata={},
            timestamp=utc_now(),
        )
        try:
            await self._event_store.append(event)
        except Exception:
            logger.exception(
                "Audit event %s for %s was NOT recorded; trading continues",
                event_type,
                aggregate_id,
                extra={"aggregate_id": aggregate_id, "event_type": event_type},
            )
