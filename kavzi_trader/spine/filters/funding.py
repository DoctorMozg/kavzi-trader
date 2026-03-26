import logging
from decimal import Decimal
from typing import Literal

from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema

logger = logging.getLogger(__name__)


class FundingRateFilter:
    """Blocks trades that go against extreme funding conditions."""

    def __init__(self, config: FilterConfigSchema) -> None:
        self._config = config

    def evaluate(
        self,
        side: Literal["LONG", "SHORT"],
        order_flow: OrderFlowSchema | None,
    ) -> FilterResultSchema:
        if order_flow is None:
            logger.warning("Order flow unavailable, funding filter skipped")
            return FilterResultSchema(
                name="funding",
                is_allowed=True,
                reason=None,
            )

        zscore = order_flow.funding_zscore
        if side == "LONG" and zscore > self._config.crowded_long_zscore:
            logger.debug(
                "Funding filter: side=%s zscore=%s > threshold=%s, blocked",
                side,
                zscore,
                self._config.crowded_long_zscore,
            )
            return FilterResultSchema(
                name="funding",
                is_allowed=False,
                reason="crowded_long",
            )
        if side == "SHORT" and zscore < self._config.crowded_short_zscore:
            logger.debug(
                "Funding filter: side=%s zscore=%s < threshold=%s, blocked",
                side,
                zscore,
                self._config.crowded_short_zscore,
            )
            return FilterResultSchema(
                name="funding",
                is_allowed=False,
                reason="crowded_short",
            )

        size_multiplier = Decimal("1.0")
        abs_zscore = abs(zscore)
        adverse = (side == "LONG" and zscore > 0) or (side == "SHORT" and zscore < 0)
        if adverse and Decimal("1.0") <= abs_zscore < Decimal("2.0"):
            size_multiplier = Decimal("0.8")
            logger.debug(
                "Funding filter: moderate adverse funding zscore=%s,"
                " reducing size to 80%%",
                zscore,
            )

        logger.debug(
            "Funding filter: side=%s zscore=%s, allowed (multiplier=%s)",
            side,
            zscore,
            size_multiplier,
        )
        return FilterResultSchema(
            name="funding",
            is_allowed=True,
            reason=None,
            size_multiplier=size_multiplier,
        )
