from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.bracket_intent_schema import BracketIntentSchema

# Becomes a union discriminated on `kind` once a second intent type exists.
StrategyIntent = BracketIntentSchema


class StrategyTickResultSchema(BaseModel):
    """What a strategy wants queued and when it wants to be called again."""

    intents: Annotated[list[StrategyIntent], Field()] = []
    next_tick_at_ms: Annotated[int, Field(ge=0)]

    model_config = ConfigDict(frozen=True)
