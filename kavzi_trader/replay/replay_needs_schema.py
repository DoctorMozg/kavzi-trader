from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ReplayNeedsSchema(BaseModel):
    """What a strategy's replay reads from the eval cache."""

    model_config = ConfigDict(frozen=True)

    symbols: Annotated[list[str], Field(min_length=1)]
    # Kline interval of the bars the replay steps through, e.g. "15m" or "4h".
    interval: str
    daily_closes: bool = False
    metrics: bool = False
