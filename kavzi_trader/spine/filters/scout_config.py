from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ScoutConfigSchema(BaseModel):
    """Deterministic scout filter configuration.

    All thresholds for the six pattern-detection criteria plus
    volatility-gate and volume-gate rules.
    """

    # --- Volatility gate (replaces the old VolatilityGate in router) ---

    # Volatility regimes that block trading outright.
    # Any regime listed here causes an immediate SKIP before criteria are checked.
    #   ["LOW", "EXTREME"] = default (blocks very quiet and spiking markets)
    #   ["EXTREME"]        = permissive (only blocks spikes, allows quiet markets)
    blocked_regimes: Annotated[
        list[str],
        Field(default_factory=lambda: ["LOW", "EXTREME"]),
    ]

    # --- ATR compression gate ---

    # Minimum ATR as a percentage of current price.
    # Below this threshold the market is too compressed for viable stop placement.
    #   0.2 = permissive (allows tighter ranges)
    #   0.3 = default (report-validated: TONUSDT ATR=0.0029 at price ~1.22 ≈ 0.24%)
    #   0.5 = strict
    atr_pct_min: Annotated[
        Decimal,
        Field(default=Decimal("0.3")),
    ]

    # --- Volume gates ---

    # Volume ratio below which SKIP is forced regardless of other signals.
    # Prevents false positives in near-zero-activity conditions.
    #   0.2 = permissive
    #   0.3 = default
    #   0.5 = strict
    vol_ratio_hard_skip: Annotated[
        Decimal,
        Field(default=Decimal("0.3")),
    ]

    # Volume ratio below which SKIP is strongly favoured.
    # A criterion must still match to override this soft gate.
    #   0.5 = permissive
    #   0.8 = default
    #   1.0 = strict
    vol_ratio_soft_skip: Annotated[
        Decimal,
        Field(default=Decimal("0.8")),
    ]

    # --- Criterion 1: BREAKOUT ---
    # Price closes beyond Bollinger Band with volume confirmation.

    # Minimum volume ratio to confirm a breakout candle.
    #   1.0 = permissive
    #   1.2 = default
    #   1.5 = strict
    breakout_vol_ratio_min: Annotated[
        Decimal,
        Field(default=Decimal("1.2")),
    ]

    # --- Criterion 2: TREND CONTINUATION ---
    # EMA alignment + RSI mid-range + volume above average.

    # RSI range that confirms a trending (not exhausted) market.
    #   30/70 = wide (accepts more)
    #   40/60 = default
    #   45/55 = strict
    trend_rsi_low: Annotated[Decimal, Field(default=Decimal(40))]
    trend_rsi_high: Annotated[Decimal, Field(default=Decimal(60))]

    # Minimum volume ratio for trend continuation.
    #   0.8 = permissive
    #   1.0 = default
    #   1.2 = strict
    trend_vol_ratio_min: Annotated[
        Decimal,
        Field(default=Decimal("1.0")),
    ]

    # --- Criterion 3: REVERSAL SIGNAL ---
    # RSI extreme + price at Bollinger Band boundary.

    # RSI thresholds for oversold / overbought.
    #   25/75 = strict (only deep extremes)
    #   30/70 = default
    #   35/65 = permissive
    reversal_rsi_oversold: Annotated[Decimal, Field(default=Decimal(30))]
    reversal_rsi_overbought: Annotated[Decimal, Field(default=Decimal(70))]

    # Bollinger %B thresholds for price at band boundary.
    #   0.05/0.95 = strict (very close to bands)
    #   0.1/0.9   = default
    #   0.15/0.85 = permissive
    reversal_percent_b_lower: Annotated[
        Decimal,
        Field(default=Decimal("0.1")),
    ]
    reversal_percent_b_upper: Annotated[
        Decimal,
        Field(default=Decimal("0.9")),
    ]

    # --- Criterion 4: VOLUME SPIKE ---
    # Large volume + large candle body + at least one supporting signal.

    # Minimum volume ratio to qualify as a spike.
    #   1.5 = permissive
    #   2.0 = default
    #   3.0 = strict
    volume_spike_ratio_min: Annotated[
        Decimal,
        Field(default=Decimal("2.0")),
    ]

    # Minimum candle body-to-range ratio for "large body" check.
    # Computed as the absolute body size divided by the candle range.
    #   0.3 = permissive (accepts smaller bodies)
    #   0.5 = default
    #   0.7 = strict (requires strong directional candle)
    volume_spike_body_ratio_min: Annotated[
        Decimal,
        Field(default=Decimal("0.5")),
    ]

    # Supporting RSI range for volume spike (outside = signal).
    #   30/70 = permissive
    #   35/65 = default
    #   40/60 = strict
    volume_spike_rsi_low: Annotated[Decimal, Field(default=Decimal(35))]
    volume_spike_rsi_high: Annotated[Decimal, Field(default=Decimal(65))]

    # Supporting Bollinger %B thresholds for volume spike.
    #   0.1/0.9   = strict (near bands)
    #   0.15/0.85 = default
    #   0.2/0.8   = permissive
    volume_spike_percent_b_lower: Annotated[
        Decimal,
        Field(default=Decimal("0.15")),
    ]
    volume_spike_percent_b_upper: Annotated[
        Decimal,
        Field(default=Decimal("0.85")),
    ]

    # --- Criterion 5: MOMENTUM SHIFT ---
    # MACD histogram sign differs from the direction of recent candles.

    # How many preceding candles must agree on the opposite direction.
    # A higher value filters out noise (single-candle fakeouts).
    #   2 = permissive (only 1 opposing candle needed)
    #   3 = default (2 consecutive opposing candles needed)
    #   4 = strict (3 consecutive opposing candles needed)
    momentum_min_candles: Annotated[int, Field(default=3, ge=2)]

    # --- Criterion 6: TREND WITH PULLBACK ---
    # EMA alignment + meaningful price movement over recent candles.

    # Minimum price change (%) over the candle window to qualify.
    #   0.5 = permissive
    #   1.5 = default
    #   2.5 = strict
    pullback_price_change_min: Annotated[
        Decimal,
        Field(default=Decimal("1.5")),
    ]

    model_config = ConfigDict(frozen=True)
