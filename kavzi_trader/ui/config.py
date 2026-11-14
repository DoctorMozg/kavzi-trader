from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class UiConfigSchema(BaseModel):
    """Dashboard publishing, streams, server binding and history limits."""

    enabled: Annotated[bool, Field()] = True
    events_stream: Annotated[str, Field(min_length=1)] = "kt:ui:events"
    # Account ticks arrive at ~1Hz; a separate short stream keeps them from
    # trimming the low-rate decision/trade history out of events_stream.
    ticks_stream: Annotated[str, Field(min_length=1)] = "kt:ui:ticks"
    events_max_len: Annotated[int, Field(ge=100)] = 20_000
    ticks_max_len: Annotated[int, Field(ge=10)] = 600
    host: Annotated[str, Field()] = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=65535)] = 8780
    static_dir: Annotated[Path, Field()] = Path("ui/web/dist")
    max_decisions: Annotated[int, Field(ge=10)] = 300
    max_trades: Annotated[int, Field(ge=10)] = 200
    max_closed_positions: Annotated[int, Field(ge=10)] = 200
    max_candles: Annotated[int, Field(ge=10)] = 500
    client_queue_size: Annotated[int, Field(ge=8)] = 256
    read_block_ms: Annotated[int, Field(ge=100)] = 2000
    snapshot_interval_s: Annotated[float, Field(gt=0)] = 1.0
    backfill_candles: Annotated[int, Field(ge=1)] = 300

    model_config = ConfigDict(frozen=True)
