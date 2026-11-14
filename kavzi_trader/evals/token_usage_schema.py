from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TokenUsageSchema(BaseModel):
    """Token counts as pydantic-ai reports them; input includes cache tokens."""

    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    cache_read_tokens: Annotated[int, Field(ge=0)] = 0
    cache_write_tokens: Annotated[int, Field(ge=0)] = 0

    model_config = ConfigDict(frozen=True)
