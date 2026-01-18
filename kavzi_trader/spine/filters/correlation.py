from decimal import Decimal

from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema
from kavzi_trader.spine.state.schemas import PositionSchema


class CorrelationFilter:
    """Reduces size when opening positions in correlated symbols."""

    def __init__(self, config: FilterConfigSchema) -> None:
        self._config = config

    def evaluate(
        self,
        symbol: str,
        positions: list[PositionSchema],
    ) -> FilterResultSchema:
        correlated = self._config.correlated_pairs.get(symbol, [])
        if not correlated:
            return FilterResultSchema(
                name="correlation",
                is_allowed=True,
                reason=None,
            )

        for position in positions:
            if position.symbol in correlated:
                return FilterResultSchema(
                    name="correlation",
                    is_allowed=True,
                    reason="correlated_exposure",
                    size_multiplier=self._config.max_correlated_exposure,
                )

        return FilterResultSchema(
            name="correlation",
            is_allowed=True,
            reason=None,
            size_multiplier=Decimal("1.0"),
        )
