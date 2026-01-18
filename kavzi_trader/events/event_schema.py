from collections.abc import Mapping
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventSchema(BaseModel):
    """Immutable event payload for audit and replay."""

    event_id: Annotated[str, Field(default_factory=lambda: str(uuid4()))]
    event_type: Annotated[str, Field(...)]
    version: Annotated[int, Field(default=1, ge=1)]
    timestamp: Annotated[datetime, Field(...)]
    aggregate_id: Annotated[str, Field(...)]
    aggregate_type: Annotated[str, Field(...)]
    data: Annotated[Mapping[str, object | None], Field(default_factory=dict)]
    metadata: Annotated[Mapping[str, object | None], Field(default_factory=dict)]

    model_config = ConfigDict(frozen=True)
