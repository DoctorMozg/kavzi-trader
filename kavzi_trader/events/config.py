from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.events.aggregate_type import AggregateType


def _default_streams() -> dict[AggregateType, str]:
    return {member: f"kt:events:{member.value}" for member in AggregateType}


class EventStoreConfigSchema(BaseModel):
    """Configuration for Redis Streams event store."""

    stream_max_length: Annotated[int, Field(ge=1)] = 100_000
    streams: Annotated[dict[AggregateType, str], Field()] = Field(
        default_factory=_default_streams,
    )

    model_config = ConfigDict(frozen=True)
