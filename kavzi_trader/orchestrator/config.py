from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class OrchestratorConfigSchema(BaseModel):
    """Configuration for orchestrator loop timing and shutdown behavior."""

    order_flow_fetch_interval_s: Annotated[int, Field(ge=1)] = 300
    reasoning_interval_s: Annotated[int, Field(ge=1)] = 60
    position_check_interval_s: Annotated[int, Field(ge=1)] = 5
    position_cycle_timeout_s: Annotated[int, Field(ge=1)] = 30
    graceful_shutdown_timeout_s: Annotated[float, Field(gt=0.0)] = 10.0
    loop_restart_base_delay_s: Annotated[float, Field(ge=0.0)] = 1.0
    loop_restart_max_delay_s: Annotated[float, Field(ge=0.0)] = 60.0
    # A loop that dies this many times within the window is not coming back.
    loop_max_crashes: Annotated[int, Field(ge=1)] = 5
    loop_crash_window_s: Annotated[float, Field(gt=0.0)] = 600.0

    model_config = ConfigDict(frozen=True)
