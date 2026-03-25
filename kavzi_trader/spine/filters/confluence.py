import logging
from decimal import Decimal
from typing import Literal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
)

logger = logging.getLogger(__name__)


class ConfluenceCalculator:
    """Scores rule-based signals to quantify setup alignment."""

    def evaluate(
        self,
        side: Literal["LONG", "SHORT"],
        candle: CandlestickSchema,
        indicators: TechnicalIndicatorsSchema,
        order_flow: OrderFlowSchema | None,
    ) -> AlgorithmConfluenceSchema:
        ema_alignment = self._ema_alignment(indicators, side)
        rsi_favorable = self._rsi_favorable(indicators, side)
        volume_above_average = self._volume_above_average(indicators)
        price_at_bollinger = self._price_at_bollinger(candle, indicators, side)
        funding_favorable = self._funding_favorable(order_flow, side)
        oi_supports_direction = self._oi_supports_direction(order_flow, side)

        score = sum(
            [
                ema_alignment,
                rsi_favorable,
                volume_above_average,
                price_at_bollinger,
                funding_favorable,
                oi_supports_direction,
            ],
        )

        if score == 0:
            logger.warning(
                "Confluence score is 0 for %s — all signals returned False,"
                " indicators may be missing",
                side,
            )
        logger.debug(
            "Confluence: ema=%s rsi=%s vol=%s boll=%s fund=%s oi=%s"
            " score=%d",
            ema_alignment, rsi_favorable, volume_above_average,
            price_at_bollinger, funding_favorable,
            oi_supports_direction, int(score),
        )

        return AlgorithmConfluenceSchema(
            ema_alignment=ema_alignment,
            rsi_favorable=rsi_favorable,
            volume_above_average=volume_above_average,
            price_at_bollinger=price_at_bollinger,
            funding_favorable=funding_favorable,
            oi_supports_direction=oi_supports_direction,
            score=int(score),
        )

    def _ema_alignment(
        self,
        indicators: TechnicalIndicatorsSchema,
        side: Literal["LONG", "SHORT"],
    ) -> bool:
        ema_20 = indicators.ema_20
        ema_50 = indicators.ema_50
        ema_200 = indicators.ema_200
        if ema_20 is None or ema_50 is None or ema_200 is None:
            return False
        if side == "LONG":
            return ema_20 > ema_50 > ema_200
        return ema_20 < ema_50 < ema_200

    def _rsi_favorable(
        self,
        indicators: TechnicalIndicatorsSchema,
        side: Literal["LONG", "SHORT"],
    ) -> bool:
        rsi = indicators.rsi_14
        if rsi is None:
            return False
        if side == "LONG":
            return Decimal("30") <= rsi <= Decimal("40")
        return Decimal("60") <= rsi <= Decimal("70")

    def _volume_above_average(
        self,
        indicators: TechnicalIndicatorsSchema,
    ) -> bool:
        volume = indicators.volume
        if volume is None:
            return False
        return volume.volume_ratio > Decimal("1.0")

    def _price_at_bollinger(
        self,
        candle: CandlestickSchema,
        indicators: TechnicalIndicatorsSchema,
        side: Literal["LONG", "SHORT"],
    ) -> bool:
        bollinger = indicators.bollinger
        if bollinger is None:
            return False
        if side == "LONG":
            return candle.close_price <= bollinger.lower
        return candle.close_price >= bollinger.upper

    def _funding_favorable(
        self,
        order_flow: OrderFlowSchema | None,
        side: Literal["LONG", "SHORT"],
    ) -> bool:
        if order_flow is None:
            return False
        if side == "LONG":
            return order_flow.funding_zscore <= Decimal("0")
        return order_flow.funding_zscore >= Decimal("0")

    def _oi_supports_direction(
        self,
        order_flow: OrderFlowSchema | None,
        side: Literal["LONG", "SHORT"],
    ) -> bool:
        if order_flow is None:
            return False
        if side == "LONG":
            return order_flow.oi_change_1h_percent > Decimal("0")
        return order_flow.oi_change_1h_percent < Decimal("0")
