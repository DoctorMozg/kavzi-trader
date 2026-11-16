from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.strategy_intent import StrategyIntent


class StrategyTickResultSchema(BaseModel):
    """What a strategy wants queued and when it wants to be called again."""

    intents: Annotated[list[StrategyIntent], Field()] = []
    next_tick_at_ms: Annotated[int, Field(ge=0)]

    model_config = ConfigDict(frozen=True)
