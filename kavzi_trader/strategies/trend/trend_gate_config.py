from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TrendGateConfigSchema(BaseModel):
    """Shadow LLM news check on trend entries; it logs and never blocks a trade."""

    enabled: bool = False
    # Odd, so a majority always exists; VETO needs more than half the samples.
    samples: Annotated[int, Field(ge=1, le=7)] = 3
    window_h: Annotated[int, Field(ge=1, le=336)] = 72
    lag_h: Annotated[float, Field(ge=0)] = 2.0
    max_headlines: Annotated[int, Field(ge=1, le=100)] = 30
    news_root: Path = Path("data/news")
    log_path: Path = Path("results/trend_gate/shadow.jsonl")

    model_config = ConfigDict(frozen=True)
