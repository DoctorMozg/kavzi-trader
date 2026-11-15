from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RunHeaderSchema(BaseModel):
    """Run configuration saved next to the results so a run can be audited."""

    run_id: Annotated[str, Field(...)]
    dataset: Annotated[str, Field(...)]
    analyst_model: Annotated[str, Field(...)]
    analyst_effort: Annotated[str, Field(...)]
    trader_model: Annotated[str, Field(...)]
    trader_effort: Annotated[str, Field(...)]
    provider: Annotated[str, Field(...)]
    bypass_scout: Annotated[bool, Field(...)]
    # Defaulted so headers of runs made before the flag existed still load.
    force_trader: bool = False
    concurrency: Annotated[int, Field(..., ge=1)]
    git_hash: str | None = None

    model_config = ConfigDict(frozen=True)
