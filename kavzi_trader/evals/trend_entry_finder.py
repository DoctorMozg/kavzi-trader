from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_entry_schema import TrendEntrySchema
from kavzi_trader.evals.weight_signal import WeightSignal
from kavzi_trader.strategies.trend.trend_following_plugin import REBALANCE_DELAY_MS
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer


class TrendEntryFinder:
    """Lists the rule's flat-to-long entries in a window, as the plugin sees them."""

    def __init__(
        self, signal: WeightSignal, buffer: TurnoverBuffer, commission_rate: float
    ) -> None:
        self._signal = signal
        self._buffer = buffer
        self._commission_rate = commission_rate

    def entries(
        self, data: TrendDataSchema, warmup_from: date, first: date, last: date
    ) -> list[TrendEntrySchema]:
        """Entries with signal day in [first, last]; buffer starts at warmup_from."""
        if not warmup_from < first <= last:
            msg = f"need warmup_from < first <= last, got {warmup_from} {first} {last}"
            raise ValueError(msg)
        closes = data.closes
        days = closes.index >= pd.Timestamp(warmup_from)
        # A buffer started inside the window would count held positions as entries.
        held = self._buffer.apply(self._signal.weights(closes)[days])
        index = closes.index[days]
        # Weights set at close of day d earn day d+1's return and funding.
        returns = closes.pct_change().shift(-1).to_numpy()[days]
        funding = data.funding.shift(-1).to_numpy()[days]
        previous = np.vstack([np.zeros(held.shape[1]), held[:-1]])
        pnl = (
            held * np.nan_to_num(returns)
            - self._commission_rate * np.abs(held - previous)
            - held * np.nan_to_num(funding)
        )
        found: list[TrendEntrySchema] = []
        for col, symbol in enumerate(closes.columns):
            for t in np.flatnonzero((previous[:, col] == 0) & (held[:, col] > 0)):
                day = index[t].date()
                if not first <= day <= last:
                    continue
                exits = np.flatnonzero(held[t:, col] == 0)
                end = t + int(exits[0]) if exits.size else len(index)
                # The exit day's row carries the cost of selling.
                closing = min(end + 1, len(index))
                found.append(
                    TrendEntrySchema(
                        symbol=str(symbol),
                        signal_day=day,
                        as_of=self._review_time(day),
                        weight=float(held[t, col]),
                        exit_day=index[end].date() if exits.size else None,
                        net_pnl=float(pnl[t:closing, col].sum()),
                    )
                )
        return sorted(found, key=lambda e: (e.signal_day, e.symbol))

    @staticmethod
    def _review_time(day: date) -> datetime:
        # The daily bar closes at the next midnight; the plugin runs just after.
        midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
        return midnight + timedelta(days=1, milliseconds=REBALANCE_DELAY_MS)
