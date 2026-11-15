from datetime import UTC, datetime
from typing import Annotated, Self

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

_MS_PER_S = 1000


class SampleWindowSchema(BaseModel):
    """Close-time range of the bars to sample; history before it still warms up."""

    start_ms: Annotated[int | None, Field()] = None
    end_ms: Annotated[int | None, Field()] = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if (
            self.start_ms is not None
            and self.end_ms is not None
            and self.start_ms >= self.end_ms
        ):
            msg = f"window start {self.start_ms} must precede end {self.end_ms}"
            raise ValueError(msg)
        return self

    def contains(self, close_ms: npt.NDArray[np.int64]) -> npt.NDArray[np.bool_]:
        """Mask of close times in [start_ms, end_ms)."""
        mask = np.ones(len(close_ms), dtype=bool)
        if self.start_ms is not None:
            mask &= close_ms >= self.start_ms
        if self.end_ms is not None:
            mask &= close_ms < self.end_ms
        return mask

    @property
    def label(self) -> str:
        if self.start_ms is None and self.end_ms is None:
            return "all cached bars"
        start = "start" if self.start_ms is None else _day(self.start_ms)
        end = "end" if self.end_ms is None else _day(self.end_ms)
        return f"bars closing from {start} to {end} (exclusive)"


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / _MS_PER_S, UTC).date().isoformat()
