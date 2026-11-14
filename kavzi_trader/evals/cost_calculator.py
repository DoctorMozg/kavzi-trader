import logging
from decimal import Decimal

from kavzi_trader.evals.model_price_schema import ModelPriceSchema
from kavzi_trader.evals.token_usage_schema import TokenUsageSchema

logger = logging.getLogger(__name__)

_TOKENS_PER_MTOK = Decimal(1_000_000)

# List prices, 5-minute cache writes.
MODEL_PRICES: dict[str, ModelPriceSchema] = {
    "claude-sonnet-5-5": ModelPriceSchema(
        input_per_mtok=Decimal(2),
        output_per_mtok=Decimal(10),
        cache_read_per_mtok=Decimal("0.10"),
        cache_write_per_mtok=Decimal("2.50"),
    ),
    "claude-opus-5-5": ModelPriceSchema(
        input_per_mtok=Decimal(4),
        output_per_mtok=Decimal(20),
        cache_read_per_mtok=Decimal("0.20"),
        cache_write_per_mtok=Decimal("5.00"),
    ),
}


class CostCalculator:
    """Prices token usage against MODEL_PRICES."""

    def __init__(self, prices: dict[str, ModelPriceSchema] | None = None) -> None:
        self._prices = MODEL_PRICES if prices is None else prices
        self._warned: set[str] = set()

    def cost_usd(self, model_id: str, usage: TokenUsageSchema) -> float | None:
        price = self._prices.get(model_id)
        if price is None:
            if model_id not in self._warned:
                self._warned.add(model_id)
                logger.warning("No price for model %s; cost recorded as None", model_id)
            return None
        # pydantic-ai's input_tokens already contains the cached tokens.
        fresh = max(
            usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens, 0
        )
        total = (
            fresh * price.input_per_mtok
            + usage.output_tokens * price.output_per_mtok
            + usage.cache_read_tokens * price.cache_read_per_mtok
            + usage.cache_write_tokens * price.cache_write_per_mtok
        )
        return float(total / _TOKENS_PER_MTOK)
