from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.brain.confluence_thresholds import signal_adjusted_threshold
from kavzi_trader.domain.algorithm_confluence import ALGO_SIGNAL_COUNT


class ConfluenceGatesSchema(BaseModel):
    """Confluence thresholds of one Analyst evaluation, scaled to its signals."""

    regime_gate: Annotated[int, Field(ge=0)]
    available_signals: Annotated[int, Field(ge=0, le=ALGO_SIGNAL_COUNT)]

    model_config = ConfigDict(frozen=True)

    def adjusted(self, threshold: int) -> int:
        """Scale a fixed full-data threshold to this evaluation's signals."""
        return signal_adjusted_threshold(threshold, self.available_signals)
