from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DatasetBuildParamsSchema(BaseModel):
    """Inputs of one dataset build; the rest comes from the bot's own config."""

    symbols: Annotated[list[str], Field(..., min_length=1)]
    interval: Annotated[str, Field(...)]
    history_candles: Annotated[int, Field(..., ge=1)]
    max_hold_time_hours: Annotated[int, Field(..., ge=1)]
    months: Annotated[float, Field(..., gt=0)]
    cases: Annotated[int, Field(..., ge=1)]
    seed: Annotated[int, Field(...)]
    data_end_ms: Annotated[int, Field(...)]
    cache_dir: Annotated[Path, Field(...)]

    model_config = ConfigDict(frozen=True)
