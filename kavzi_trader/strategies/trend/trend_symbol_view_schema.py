from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.trend.trend_day_view_schema import TrendDayViewSchema


class TrendSymbolViewSchema(BaseModel):
    """What the trend rule sees for one symbol after the last closed day."""

    symbol: Annotated[str, Field(min_length=1)]
    signal: Annotated[float, Field(ge=-1, le=1)]
    close: Annotated[float, Field(gt=0)]
    # The next checked close above entry_level (below exit_level) flips the state.
    entry_level: Annotated[float, Field(gt=0)]
    exit_level: Annotated[float, Field(gt=0)]
    annual_vol: Annotated[float | None, Field(ge=0)] = None
    days: Annotated[list[TrendDayViewSchema], Field()]

    model_config = ConfigDict(frozen=True)
