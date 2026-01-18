from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class OrchestratorConfigSchema(BaseModel):
    """Configuration for orchestrator loop timing and shutdown behavior."""

    ws_reconnect_delay_s: Annotated[float, Field(ge=0.0)] = 1.0
    ws_max_reconnect_delay_s: Annotated[float, Field(ge=1.0)] = 60.0
    order_flow_fetch_interval_s: Annotated[int, Field(ge=1)] = 60
    position_check_interval_s: Annotated[int, Field(ge=1)] = 5
    health_check_interval_s: Annotated[int, Field(ge=1)] = 30
    graceful_shutdown_timeout_s: Annotated[int, Field(ge=1)] = 10

    model_config = ConfigDict(frozen=True)
