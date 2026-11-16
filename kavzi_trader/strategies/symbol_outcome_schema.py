from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.bracket_intent_schema import BracketIntentSchema


class SymbolOutcomeSchema(BaseModel):
    """Result of one symbol's pass through the LLM pipeline."""

    interesting: Annotated[bool, Field()]
    intent: Annotated[BracketIntentSchema | None, Field()] = None

    model_config = ConfigDict(frozen=True)
