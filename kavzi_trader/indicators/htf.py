"""Higher-timeframe (1h) trend derived from cached 15m candles.

Aggregating locally avoids a second market-data stream: the reasoning loop
already caches enough 15m history to reconstruct a 1h EMA trend each cycle.
"""

from decimal import Decimal
from typing import Annotated, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.momentum import calculate_rsi
from kavzi_trader.indicators.trend import calculate_ema

# 1h candles needed before the EMA50 stack is trustworthy. Below this the
# trend is reported NEUTRAL rather than guessed from a short stack.
_MIN_BARS_1H = 50

# RSI midline. Above it confirms bullish momentum for a LONG bias, below it
# confirms bearish momentum for SHORT; exactly 50 is treated as neutral.
_RSI_MIDLINE = Decimal(50)

HtfDirection = Literal["LONG", "SHORT", "NEUTRAL"]


class HtfTrendSchema(BaseModel):
    """1h trend context: direction plus the values that produced it."""

    direction: Annotated[HtfDirection, Field(...)]
    ema_20: Annotated[Decimal | None, Field(default=None)]
    ema_50: Annotated[Decimal | None, Field(default=None)]
    rsi_14: Annotated[Decimal | None, Field(default=None)]
    bars_1h: Annotated[int, Field(..., ge=0)]

    model_config = ConfigDict(frozen=True)


def aggregate_1h_closes(candles_15m: list[CandlestickSchema]) -> list[Decimal]:
    """Reduce ordered 15m candles to one close price per clock hour.

    Each hour bucket's close is the close of its last 15m candle within the
    bucket — the standard resample-to-1h close.
    """
    closes: list[Decimal] = []
    current_bucket: tuple[int, int, int, int] | None = None
    for candle in candles_15m:
        t = candle.open_time
        bucket = (t.year, t.month, t.day, t.hour)
        if bucket != current_bucket:
            closes.append(candle.close_price)
            current_bucket = bucket
        else:
            closes[-1] = candle.close_price
    return closes


def compute_htf_trend(candles_15m: list[CandlestickSchema]) -> HtfTrendSchema:
    """Derive the 1h trend from a window of 15m candles.

    LONG when the 1h EMA20 leads EMA50 with RSI confirming (>50); SHORT for
    the mirror; NEUTRAL when the stack is mixed or history is too short.
    """
    closes = aggregate_1h_closes(candles_15m)
    bars = len(closes)
    if bars < _MIN_BARS_1H:
        return HtfTrendSchema(
            direction="NEUTRAL",
            ema_20=None,
            ema_50=None,
            rsi_14=None,
            bars_1h=bars,
        )

    series = pd.Series([float(c) for c in closes])
    ema_20 = calculate_ema(series, 20)
    ema_50 = calculate_ema(series, 50)
    rsi_14 = calculate_rsi(series, 14)

    direction: HtfDirection = "NEUTRAL"
    if ema_20 is not None and ema_50 is not None and rsi_14 is not None:
        if ema_20 > ema_50 and rsi_14 > _RSI_MIDLINE:
            direction = "LONG"
        elif ema_20 < ema_50 and rsi_14 < _RSI_MIDLINE:
            direction = "SHORT"

    return HtfTrendSchema(
        direction=direction,
        ema_20=ema_20,
        ema_50=ema_50,
        rsi_14=rsi_14,
        bars_1h=bars,
    )
