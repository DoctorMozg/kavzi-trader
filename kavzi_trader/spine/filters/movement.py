from decimal import Decimal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema


class MinimumMovementFilter:
    """Skips candles without sufficient price movement for a setup."""

    def __init__(self, config: FilterConfigSchema) -> None:
        self._config = config

    def evaluate(
        self,
        candle: CandlestickSchema,
        atr: Decimal | None,
    ) -> FilterResultSchema:
        if atr is None or atr <= 0:
            return FilterResultSchema(
                name="movement",
                is_allowed=True,
                reason=None,
            )

        body = abs(candle.close_price - candle.open_price)
        ratio = body / atr

        if ratio < self._config.min_body_atr_ratio:
            return FilterResultSchema(
                name="movement",
                is_allowed=False,
                reason="small_body",
            )

        return FilterResultSchema(
            name="movement",
            is_allowed=True,
            reason=None,
        )
