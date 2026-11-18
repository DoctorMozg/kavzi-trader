from typing import Annotated

from pydantic import BaseModel, ConfigDict, SkipValidation

from kavzi_trader.external.loop import ExternalSentimentLoop
from kavzi_trader.orchestrator.loops.strategy import StrategyLoop
from kavzi_trader.strategies.trend.gate_inputs_reader import GateInputsReader


class StrategyWiringSchema(BaseModel):
    """The strategy loop, plus the side loops and readers only one path uses."""

    loop: Annotated[StrategyLoop, SkipValidation]
    external_loop: Annotated[ExternalSentimentLoop | None, SkipValidation] = None
    gate_inputs: Annotated[GateInputsReader | None, SkipValidation] = None

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
