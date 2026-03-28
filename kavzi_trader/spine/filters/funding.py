import logging
from decimal import Decimal
from typing import Literal

from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry

logger = logging.getLogger(__name__)


class FundingRateFilter:
    """Blocks trades that go against extreme funding conditions."""

    def __init__(
        self,
        config: FilterConfigSchema,
        tier_registry: SymbolTierRegistry | None = None,
    ) -> None:
        self._config = config
        self._tier_registry = tier_registry

    def evaluate(
        self,
        side: Literal["LONG", "SHORT"],
        order_flow: OrderFlowSchema | None,
        symbol: str | None = None,
    ) -> FilterResultSchema:
        if order_flow is None:
            logger.warning("Order flow unavailable, funding filter skipped")
            return FilterResultSchema(
                name="funding",
                is_allowed=True,
                reason=None,
            )

        zscore = order_flow.funding_zscore

        # Tier-aware thresholds
        crowded_long = self._config.crowded_long_zscore
        crowded_short = self._config.crowded_short_zscore
        if self._tier_registry is not None and symbol is not None:
            tier_config = self._tier_registry.get_config(symbol)
            crowded_long = tier_config.crowded_long_zscore
            crowded_short = tier_config.crowded_short_zscore

        if side == "LONG" and zscore > crowded_long:
            logger.debug(
                "Funding filter: side=%s zscore=%s > threshold=%s, blocked",
                side,
                zscore,
                crowded_long,
            )
            return FilterResultSchema(
                name="funding",
                is_allowed=False,
                reason="crowded_long",
            )
        if side == "SHORT" and zscore < crowded_short:
            logger.debug(
                "Funding filter: side=%s zscore=%s < threshold=%s, blocked",
                side,
                zscore,
                crowded_short,
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
