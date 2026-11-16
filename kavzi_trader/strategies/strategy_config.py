from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.strategies.trend.trend_following_config import (
    TrendFollowingConfigSchema,
)


class StrategyConfigSchema(BaseModel):
    """Selects which strategy plugin feeds the execution queue."""

    active: Annotated[Literal["llm_pipeline", "trend_following"], Field()] = (
        "llm_pipeline"
    )
    trend_following: Annotated[
        TrendFollowingConfigSchema,
        Field(default_factory=TrendFollowingConfigSchema),
    ]

    model_config = ConfigDict(frozen=True)
