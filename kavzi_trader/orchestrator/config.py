from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrchestratorConfigSchema(BaseModel):
    """Configuration for orchestrator loop timing and shutdown behavior."""

    ws_reconnect_delay_s: Annotated[float, Field(ge=0.0)] = 1.0
    ws_max_reconnect_delay_s: Annotated[float, Field(ge=1.0)] = 60.0
    order_flow_fetch_interval_s: Annotated[int, Field(ge=1)] = 60
    reasoning_interval_s: Annotated[int, Field(ge=1)] = 30
    position_check_interval_s: Annotated[int, Field(ge=1)] = 5
    health_check_interval_s: Annotated[int, Field(ge=1)] = 30
    graceful_shutdown_timeout_s: Annotated[int, Field(ge=1)] = 10

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _validate_delays(self) -> Self:
        if self.ws_reconnect_delay_s >= self.ws_max_reconnect_delay_s:
            msg = "ws_reconnect_delay_s must be < ws_max_reconnect_delay_s"
            raise ValueError(msg)
        return self
