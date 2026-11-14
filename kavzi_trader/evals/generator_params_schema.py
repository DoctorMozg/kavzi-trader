from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class GeneratorParamsSchema(BaseModel):
    """Everything besides the seed that determines which cases are generated."""

    months: Annotated[float, Field(..., gt=0)]
    cases: Annotated[int, Field(..., ge=1)]
    symbols: Annotated[list[str], Field(..., min_length=1)]
    interval: Annotated[str, Field(...)]
    history_candles: Annotated[int, Field(..., ge=1)]
    horizon_bars: Annotated[int, Field(..., ge=1)]
    min_spacing_bars: Annotated[int, Field(..., ge=1)]
    window_start_ms: Annotated[int, Field(...)]
    data_end_ms: Annotated[int, Field(...)]
    stop_atr_by_regime: Annotated[dict[str, float], Field(...)]
    tp_style: Annotated[str, Field(default="ATR_2X")]
    min_rr_ratio: Annotated[float, Field(...)]

    model_config = ConfigDict(frozen=True)
