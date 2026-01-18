from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


def _default_streams() -> dict[str, str]:
    return {
        "orders": "kt:events:orders",
        "positions": "kt:events:positions",
        "decisions": "kt:events:decisions",
        "system": "kt:events:system",
        "liquidations": "kt:events:liquidations",
    }


class EventStoreConfigSchema(BaseModel):
    """Configuration for Redis Streams event store."""

    stream_max_length: Annotated[int, Field(ge=1)] = 100_000
    retention_days: Annotated[int, Field(ge=1)] = 90
    streams: Annotated[dict[str, str], Field()] = Field(
        default_factory=_default_streams,
    )

    model_config = ConfigDict(frozen=True)
