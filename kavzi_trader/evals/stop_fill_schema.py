from pydantic import BaseModel, ConfigDict


class StopFillSchema(BaseModel):
    """A disaster stop that fired during a replay."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    minute: str
    # Fill price relative to the previous close the stop was set from.
    fill_return: float

    def describe(self) -> str:
        return f"{self.symbol} {self.minute} fill {self.fill_return:+.1%}"
