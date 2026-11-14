from typing import Annotated

from pydantic import BaseModel, ConfigDict, SkipValidation

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.ui.recorder import UiEventRecorder


class RuntimeServicesSchema(BaseModel):
    """Long-lived services shared by every subsystem the composer builds."""

    # Service objects are wired by the composer, not parsed from data, so the
    # fields skip validation (several are Protocols that cannot be isinstance-checked).
    exchange: Annotated[ExchangeClient, SkipValidation]
    state_manager: Annotated[StateManager, SkipValidation]
    redis_client: Annotated[RedisStateClient, SkipValidation]
    event_store: Annotated[RedisEventStore, SkipValidation]
    ui_recorder: Annotated[UiEventRecorder | None, SkipValidation]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
