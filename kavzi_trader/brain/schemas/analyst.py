from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class KeyLevelSchema(BaseModel):
    """
    A price level that may act as support or resistance.
    """

    price: Annotated[Decimal, Field(...)]
    level_type: Annotated[Literal["SUPPORT", "RESISTANCE"], Field(...)]
    reason: Annotated[str, Field(..., max_length=80)]

    model_config = ConfigDict(frozen=True)


class KeyLevelsSchema(BaseModel):
    """
    Collection of key price levels highlighted by the Analyst agent.
    """

    levels: Annotated[list[KeyLevelSchema], Field(default_factory=list, max_length=4)]

    model_config = ConfigDict(frozen=True)


class AnalystDecisionSchema(BaseModel):
    """
    Detailed analysis result that confirms whether a setup is valid.

    The Analyst agent checks market structure, trend context, and confluence
    signals to decide if the setup is worth a final trading decision.

    ``setup_valid`` is the LLM's own boolean judgment. ``confluence_score``
    is a parallel integer signal (0-11). The router applies a hysteresis
    gate on confluence to avoid flipping on near-threshold sampling noise;
    see ``AgentRouter._ANALYST_CONFLUENCE_ENTER``.
    """

    setup_valid: Annotated[bool, Field(...)]
    direction: Annotated[Literal["LONG", "SHORT", "NEUTRAL"], Field(...)]
    confluence_score: Annotated[int, Field(..., ge=0, le=11)]
    key_levels: Annotated[KeyLevelsSchema, Field(...)]
    reasoning: Annotated[str, Field(..., min_length=60, max_length=800)]

    model_config = ConfigDict(frozen=True)
