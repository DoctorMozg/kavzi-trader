import logging
from decimal import Decimal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema

logger = logging.getLogger(__name__)


class SpikeCooldownFilter:
    """Rejects entry when the most recent candle is an impulse spike.

    If the candle body exceeds ``spike_body_atr_threshold * ATR``, the
    price has likely already moved too far for a safe entry and needs
    a confirmation candle first.
    """

    def __init__(self, config: FilterConfigSchema) -> None:
        self._threshold = config.spike_body_atr_threshold

    def evaluate(
        self,
        candle: CandlestickSchema,
        atr: Decimal | None,
    ) -> FilterResultSchema:
        if atr is None or atr <= 0:
            logger.warning(
                "ATR is %s, spike cooldown filter bypassed",
                atr,
            )
            return FilterResultSchema(
                name="spike_cooldown",
                is_allowed=True,
                reason=None,
            )

        body = abs(candle.close_price - candle.open_price)
        ratio = body / atr

        logger.debug(
            "Spike cooldown filter: body/ATR ratio=%s threshold=%s",
            ratio,
            self._threshold,
        )

        if ratio > self._threshold:
            return FilterResultSchema(
                name="spike_cooldown",
                is_allowed=False,
                reason=f"spike_detected (body/ATR={ratio:.2f})",
            )

        return FilterResultSchema(
            name="spike_cooldown",
            is_allowed=True,
            reason=None,
        )
