from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class GateInputsSchema(BaseModel):
    """What the shadow gate would read if an entry fired right now."""

    model_id: Annotated[str, Field(min_length=1)]
    samples: Annotated[int, Field(ge=1)]
    prompt_sha: Annotated[str, Field(min_length=1)]
    window_h: Annotated[int, Field(ge=1)]
    lag_h: Annotated[float, Field(ge=0)]
    headlines: Annotated[int, Field(ge=0)]
    newest_at: Annotated[AwareDatetime | None, Field()] = None
    # Headlines tagged with each coin; untagged ones are market-wide news.
    coin_headlines: Annotated[dict[str, int], Field()]

    model_config = ConfigDict(frozen=True)
