from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReplayVariantSchema(BaseModel):
    """How positions are protected during one replayed day."""

    model_config = ConfigDict(frozen=True)

    name: str
    # Which 1m low trips the disaster stop: Binance's default is the last price.
    trigger: Literal["none", "contract", "mark"]
    # A STOP_MARKET fills at market: at best the stop, at worst the minute's low.
    fill: Literal["stop", "low"] = "low"
    # Per symbol, the open time (ms) of the first minute held at half size.
    halve_from_ms: dict[str, int] = Field(default_factory=dict)
