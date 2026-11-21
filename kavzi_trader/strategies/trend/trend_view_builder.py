import math

import numpy as np

from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_day_view_schema import TrendDayViewSchema
from kavzi_trader.strategies.trend.trend_rule_state_schema import (
    TrendRuleStateSchema,
)
from kavzi_trader.strategies.trend.trend_symbol_view_schema import (
    TrendSymbolViewSchema,
)

DAY_MS = 86_400_000


def _finite(value: float) -> float | None:
    return None if math.isnan(value) else float(value)


class TrendViewBuilder:
    """Turns one symbol's daily closes and rule states into what the UI shows."""

    def __init__(
        self, signal: DonchianTrendSignal, lookback: int, days_shown: int
    ) -> None:
        self._signal = signal
        # The shortest lookback breaks first, so its channel is the entry trigger.
        self._lookback = lookback
        self._days_shown = days_shown

    def symbol_view(
        self,
        symbol: str,
        closes: np.ndarray,
        rule: TrendRuleStateSchema,
        last_day_ms: int,
    ) -> TrendSymbolViewSchema:
        """`last_day_ms` is the open time of closes[-1]; days are contiguous."""
        if len(closes) == 0:
            msg = f"{symbol}: no daily closes to build a trend view from"
            raise ValueError(msg)
        if len(rule.day_states) != len(closes):
            msg = f"{symbol}: {len(rule.day_states)} states for {len(closes)} closes"
            raise ValueError(msg)
        signal = rule.day_states
        channel = self._signal.channel(closes, self._lookback)
        vol = self._signal.annual_vol(closes)
        exits = self._signal.exit_level(channel.upper, channel.lower)
        first = max(0, len(closes) - self._days_shown)
        days = [
            TrendDayViewSchema(
                day_ms=last_day_ms - (len(closes) - 1 - i) * DAY_MS,
                close=float(closes[i]),
                upper=_finite(channel.upper[i]),
                lower=_finite(channel.lower[i]),
                exit=_finite(exits[i]),
                signal=float(signal[i]),
            )
            for i in range(first, len(closes))
        ]
        recent = closes[-self._lookback :]
        return TrendSymbolViewSchema(
            symbol=symbol,
            signal=rule.state,
            close=float(closes[-1]),
            entry_level=float(recent.max()),
            exit_level=self._signal.exit_level(
                float(recent.max()), float(recent.min())
            ),
            annual_vol=_finite(vol[-1]),
            days=days,
        )
