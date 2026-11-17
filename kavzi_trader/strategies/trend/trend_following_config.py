from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.trend.trend_gate_config import TrendGateConfigSchema

DEFAULT_TREND_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
]


class TrendFollowingConfigSchema(BaseModel):
    """Rule constants of the daily Donchian trend plugin, as preregistered."""

    symbols: Annotated[list[str], Field(min_length=1)] = DEFAULT_TREND_SYMBOLS
    lookbacks: Annotated[list[int], Field(min_length=1)] = [20]
    vol_window: Annotated[int, Field(ge=2)] = 30
    annual_vol_target: Annotated[float, Field(gt=0)] = 0.25
    max_leverage: Annotated[float, Field(gt=0)] = 2.0
    buffer_band: Annotated[float, Field(ge=0)] = 0.2
    disaster_stop_pct: Annotated[Decimal, Field(gt=0, lt=1)] = Decimal("0.3")
    gate: Annotated[TrendGateConfigSchema, Field(default_factory=TrendGateConfigSchema)]

    model_config = ConfigDict(frozen=True)
