from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class UiConfigSchema(BaseModel):
    """Dashboard streams, server binding and in-memory history limits."""

    events_stream: Annotated[str, Field(default="kt:ui:events", min_length=1)]
    # Account ticks arrive at ~1Hz; a separate short stream keeps them from
    # trimming the low-rate decision/trade history out of events_stream.
    ticks_stream: Annotated[str, Field(default="kt:ui:ticks", min_length=1)]
    events_max_len: Annotated[int, Field(default=20_000, ge=100)]
    ticks_max_len: Annotated[int, Field(default=600, ge=10)]
    host: Annotated[str, Field(default="127.0.0.1")]
    port: Annotated[int, Field(default=8765, ge=1, le=65535)]
    static_dir: Annotated[Path, Field(default=Path("ui/web/dist"))]
    max_decisions: Annotated[int, Field(default=300, ge=10)]
    max_trades: Annotated[int, Field(default=200, ge=10)]
    max_closed_positions: Annotated[int, Field(default=200, ge=10)]
    max_candles: Annotated[int, Field(default=500, ge=10)]
    client_queue_size: Annotated[int, Field(default=256, ge=8)]
    read_block_ms: Annotated[int, Field(default=2000, ge=100)]

    model_config = ConfigDict(frozen=True)
