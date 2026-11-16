from typing import Annotated

from pydantic import BaseModel, ConfigDict, SkipValidation

from kavzi_trader.external.loop import ExternalSentimentLoop
from kavzi_trader.orchestrator.loops.strategy import StrategyLoop


class StrategyWiringSchema(BaseModel):
    """The strategy loop, plus the sentiment loop only the LLM path runs."""

    loop: Annotated[StrategyLoop, SkipValidation]
    external_loop: Annotated[ExternalSentimentLoop | None, SkipValidation] = None

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
