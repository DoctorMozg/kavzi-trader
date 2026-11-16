from typing import Annotated

from pydantic import Discriminator, Tag, TypeAdapter

from kavzi_trader.strategies.bracket_intent_schema import BracketIntentSchema
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)


def _intent_kind(value: object) -> str:
    # Payloads queued before `kind` existed are brackets.
    if isinstance(value, dict):
        return str(value.get("kind", "bracket"))
    return str(getattr(value, "kind", "bracket"))


StrategyIntent = Annotated[
    Annotated[BracketIntentSchema, Tag("bracket")]
    | Annotated[TargetWeightIntentSchema, Tag("target_weight")],
    Discriminator(_intent_kind),
]

STRATEGY_INTENT_ADAPTER: TypeAdapter[StrategyIntent] = TypeAdapter(StrategyIntent)


def intent_id(intent: StrategyIntent) -> str:
    """Queue-level identity: decision_id for brackets, intent_id otherwise."""
    if isinstance(intent, BracketIntentSchema):
        return intent.decision_id
    return intent.intent_id
