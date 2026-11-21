import numpy as np

from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal


class ChannelStateMachine:
    """Long/flat state of a daily Donchian channel checked at any bar closes.

    Daily bars checked once a day give the daily rule; 6h bars give B-6h of
    evals/preregistrations/2026_11_20_trend_timing.md.
    """

    def __init__(self, signal: DonchianTrendSignal) -> None:
        self._signal = signal

    def states(
        self,
        daily_closes: np.ndarray,
        bar_closes: np.ndarray,
        bar_days: np.ndarray,
        lookback: int,
    ) -> np.ndarray:
        """State after each bar close, oldest first.

        ``bar_days[b]`` is the daily index whose close bar b closes at or before;
        it faces the levels of the ``lookback`` daily closes before that day, and
        may be ``len(daily_closes)`` for bars of the still-forming day.
        """
        if bar_closes.shape != bar_days.shape:
            msg = f"{bar_closes.shape} bar closes but {bar_days.shape} bar days"
            raise ValueError(msg)
        # The extra NaN day gives the forming day its levels, which need no close.
        channel = self._signal.channel(np.append(daily_closes, np.nan), lookback)
        upper = channel.upper[bar_days]
        exit_ = self._signal.exit_level(channel.upper, channel.lower)[bar_days]
        states = np.zeros(len(bar_closes))
        current = 0.0
        for b, price in enumerate(bar_closes):
            # NaN levels or prices compare False and leave the state alone.
            if price > upper[b]:
                current = 1.0
            elif price < exit_[b]:
                current = 0.0
            states[b] = current
        return states
