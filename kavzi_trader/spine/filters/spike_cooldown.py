import logging
from decimal import Decimal
from typing import Literal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema

logger = logging.getLogger(__name__)


class SpikeCooldownFilter:
    """Rejects entry when the most recent candle is an impulse spike
    in the same direction as the trade (chasing).

    If the candle body exceeds ``spike_body_atr_threshold * ATR`` **and**
    the trade direction matches the spike direction, the price has likely
    already moved too far for a safe entry.  Reversal entries (e.g. SHORT
    after a bullish spike) are allowed because the spike is the setup
    trigger, not the risk.
    """

    def __init__(self, config: FilterConfigSchema) -> None:
        self._threshold = config.spike_body_atr_threshold

    def evaluate(
        self,
        candle: CandlestickSchema,
        atr: Decimal | None,
        side: Literal["LONG", "SHORT"] = "LONG",
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
            "Spike cooldown filter: body/ATR ratio=%s threshold=%s side=%s",
            ratio,
            self._threshold,
            side,
        )

        if ratio > self._threshold:
            # Bullish candle: close > open.  Bearish or doji: close <= open.
            bullish_candle = candle.close_price > candle.open_price
            chasing = (side == "LONG" and bullish_candle) or (
                side == "SHORT" and not bullish_candle
            )

            if chasing:
                return FilterResultSchema(
                    name="spike_cooldown",
                    is_allowed=False,
                    reason=(f"spike_detected chasing {side} (body/ATR={ratio:.2f})"),
                )

            logger.info(
                "Spike cooldown: reversal %s allowed despite body/ATR=%s (candle %s)",
                side,
                ratio,
                "bullish" if bullish_candle else "bearish",
            )

        return FilterResultSchema(
            name="spike_cooldown",
            is_allowed=True,
            reason=None,
        )
