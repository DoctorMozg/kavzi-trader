from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.domain.state_schemas import AccountStateSchema, PositionSchema


class StrategyTickSchema(BaseModel):
    """Snapshot handed to a strategy each time it is asked for intents."""

    now_ms: Annotated[int, Field(ge=0)]
    account: Annotated[AccountStateSchema | None, Field()] = None
    # Pydantic copies mutable defaults per instance, so [] is safe here.
    positions: Annotated[list[PositionSchema], Field()] = []

    model_config = ConfigDict(frozen=True)
