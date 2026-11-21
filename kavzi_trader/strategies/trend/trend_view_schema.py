from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.trend.trend_following_config import (
    TrendCheckHours,
    TrendExitRule,
)
from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema
from kavzi_trader.strategies.trend.trend_symbol_view_schema import (
    TrendSymbolViewSchema,
)
from kavzi_trader.strategies.trend.vol_spike_config import VolSpikeConfigSchema
from kavzi_trader.strategies.trend.vol_spike_reading_schema import (
    VolSpikeReadingSchema,
)


class TrendViewSchema(BaseModel):
    """The trend rule's state for every symbol, reported at each check."""

    day: Annotated[date, Field()]
    lookback: Annotated[int, Field(ge=1)]
    exit_rule: Annotated[TrendExitRule, Field()]
    check_hours: Annotated[TrendCheckHours, Field()]
    next_rebalance_ms: Annotated[int, Field(ge=0)]
    # False when the view is a restart re-report of a day already rebalanced.
    rebalanced: Annotated[bool, Field()]
    symbols: Annotated[list[TrendSymbolViewSchema], Field()]
    # Raw rule target and the buffered weight the rule holds, before any halving.
    target_weights: Annotated[dict[str, float], Field()]
    held_weights: Annotated[dict[str, float], Field()]
    # Sizing rule: weight = signal * min(vol_target / vol, max_leverage) / N.
    annual_vol_target: Annotated[float, Field(gt=0)]
    max_leverage: Annotated[float, Field(gt=0)]
    vol_window: Annotated[int, Field(ge=2)]
    buffer_band: Annotated[float, Field(ge=0)]
    disaster_stop_pct: Annotated[float, Field(gt=0, lt=1)]
    # None when vol-spike halving is off (replays have no 1m bars).
    vol_spike: Annotated[VolSpikeConfigSchema | None, Field()] = None
    # Latest closed-hour reading of each held symbol, and today's halvings.
    spikes: Annotated[dict[str, VolSpikeReadingSchema], Field()] = {}
    halvings: Annotated[dict[str, TrendHalvingSchema], Field()] = {}

    model_config = ConfigDict(frozen=True)
