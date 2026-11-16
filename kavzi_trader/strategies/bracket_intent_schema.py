from typing import Annotated, Literal

from pydantic import Field

from kavzi_trader.domain.decision_message import DecisionMessageSchema


class BracketIntentSchema(DecisionMessageSchema):
    """Entry with explicit SL/TP; the only intent kind the queue carries today."""

    # Defaults keep payloads queued before the plugin refactor parseable.
    kind: Annotated[Literal["bracket"], Field()] = "bracket"
    strategy: Annotated[str, Field()] = "llm_pipeline"
