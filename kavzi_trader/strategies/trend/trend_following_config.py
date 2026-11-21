from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kavzi_trader.strategies.trend.trend_gate_config import TrendGateConfigSchema
from kavzi_trader.strategies.trend.vol_spike_config import VolSpikeConfigSchema

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

# "low" exits below the channel low; "mid" below its midpoint (adopted 2026-11-20).
type TrendExitRule = Literal["low", "mid"]
# Hours between checks of the daily channel: 24 is the daily rule, 6 is B-6h
# (owner's choice of 2026-11-21 after an INCONCLUSIVE holdout, evals/README.md).
type TrendCheckHours = Literal[6, 24]
DAILY_CHECK_HOURS = 24


class TrendFollowingConfigSchema(BaseModel):
    """Rule constants of the Donchian trend plugin."""

    symbols: Annotated[list[str], Field(min_length=1)] = DEFAULT_TREND_SYMBOLS
    lookbacks: Annotated[list[int], Field(min_length=1)] = [20]
    exit_rule: TrendExitRule = "mid"
    check_hours: TrendCheckHours = 6
    vol_window: Annotated[int, Field(ge=2)] = 30
    annual_vol_target: Annotated[float, Field(gt=0)] = 0.25
    max_leverage: Annotated[float, Field(gt=0)] = 2.0
    buffer_band: Annotated[float, Field(ge=0)] = 0.2
    disaster_stop_pct: Annotated[Decimal, Field(gt=0, lt=1)] = Decimal("0.3")
    # Exchange leverage of each leg: it sets margin and liquidation, never size.
    leverage: Annotated[int, Field(ge=1)] = 2
    vol_spike: Annotated[
        VolSpikeConfigSchema, Field(default_factory=VolSpikeConfigSchema)
    ]
    gate: Annotated[TrendGateConfigSchema, Field(default_factory=TrendGateConfigSchema)]

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _one_lookback_off_daily(self) -> TrendFollowingConfigSchema:
        if self.check_hours != DAILY_CHECK_HOURS and len(self.lookbacks) != 1:
            msg = (
                f"check_hours {self.check_hours} needs one lookback, "
                f"got {self.lookbacks}"
            )
            raise ValueError(msg)
        return self
