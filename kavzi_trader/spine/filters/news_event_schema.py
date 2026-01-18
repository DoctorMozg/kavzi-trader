from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class NewsEventSchema(BaseModel):
    """Represents a scheduled market event window for blocking trades."""

    name: Annotated[str, Field(...)]
    start_time: Annotated[datetime, Field(...)]
    end_time: Annotated[datetime, Field(...)]

    model_config = ConfigDict(frozen=True)
