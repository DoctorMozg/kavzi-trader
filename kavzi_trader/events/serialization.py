import json
from datetime import datetime
from typing import TypedDict

from kavzi_trader.events.event_schema import EventSchema


class SerializedEventDict(TypedDict):
    """Redis stream field layout for a serialized event."""

    event_id: str
    event_type: str
    version: str
    timestamp: str
    aggregate_id: str
    aggregate_type: str
    data: str
    metadata: str


def serialize_event(event: EventSchema) -> SerializedEventDict:
    """Serialize an event into Redis stream fields."""

    return SerializedEventDict(
        event_id=event.event_id,
        event_type=event.event_type,
        version=str(event.version),
        timestamp=event.timestamp.isoformat(),
        aggregate_id=event.aggregate_id,
        aggregate_type=event.aggregate_type,
        data=json.dumps(event.data),
        metadata=json.dumps(event.metadata),
    )


def deserialize_event(fields: SerializedEventDict) -> EventSchema:
    """Deserialize Redis stream fields into an EventSchema."""

    return EventSchema(
        event_id=fields["event_id"],
        event_type=fields["event_type"],
        version=int(fields["version"]),
        timestamp=datetime.fromisoformat(fields["timestamp"]),
        aggregate_id=fields["aggregate_id"],
        aggregate_type=fields["aggregate_type"],
        data=json.loads(fields.get("data", "{}")),
        metadata=json.loads(fields.get("metadata", "{}")),
    )
