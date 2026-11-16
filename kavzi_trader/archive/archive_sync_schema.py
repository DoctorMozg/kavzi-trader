from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ArchiveSyncSchema(BaseModel):
    """What one symbol's sync of one dataset did."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    dataset: str
    fetched: Annotated[int, Field(ge=0)]
    # Months already stored by an earlier run.
    skipped: Annotated[int, Field(ge=0)]
