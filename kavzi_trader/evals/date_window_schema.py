from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator


class DateWindowSchema(BaseModel):
    """An inclusive range of UTC days."""

    model_config = ConfigDict(frozen=True)

    first_day: date
    last_day: date

    @model_validator(mode="after")
    def _ordered(self) -> DateWindowSchema:
        if self.first_day > self.last_day:
            msg = f"first_day {self.first_day} is after last_day {self.last_day}"
            raise ValueError(msg)
        return self
