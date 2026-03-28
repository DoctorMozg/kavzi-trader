from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DateRangeSchema(BaseModel):
    start: datetime
    end: datetime | None = None
    model_config = ConfigDict(frozen=True)
