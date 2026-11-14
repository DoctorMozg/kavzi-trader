from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.domain.algorithm_confluence import AlgorithmConfluenceSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema


class FilterChainResultSchema(BaseModel):
    """Aggregates all filter outcomes and overall pass/fail state."""

    is_allowed: Annotated[bool, Field(...)]
    rejection_reason: Annotated[str | None, Field(default=None)]
    size_multiplier: Annotated[Decimal, Field(default=Decimal("1.0"))]
    results: Annotated[list[FilterResultSchema], Field(default_factory=list)]
    confluence: Annotated[AlgorithmConfluenceSchema | None, Field(default=None)]
    volatility_regime: Annotated[VolatilityRegime | None, Field(default=None)]
    volatility_zscore: Annotated[Decimal | None, Field(default=None)]

    model_config = ConfigDict(frozen=True)
