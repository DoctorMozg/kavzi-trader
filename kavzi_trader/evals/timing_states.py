import numpy as np

from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal


class TimingStates:
    """Long/flat states of the mid-exit Donchian rule, one per bar close.

    Each state depends on prices known at that bar's close only.
    """

    def __init__(self, signal: MidExitTrendSignal, lookback: int) -> None:
        self._signal = signal
        self._lookback = lookback

    def on_bars(self, bar_closes: np.ndarray) -> np.ndarray:
        """The rule on the bars themselves: lookback counted in bars (arm A).

        ``bar_closes`` is (bars, symbols).
        """
        # compute() also sizes the weight on bar returns; only its state is used.
        columns = [self._signal.compute(c, 1).signal for c in bar_closes.T]
        return np.column_stack(columns)

    def on_daily_channel(
        self, daily_closes: np.ndarray, bar_closes: np.ndarray, per_day: int
    ) -> np.ndarray:
        """Daily-channel levels against every bar close (arm B).

        Bars closing during UTC day x face the levels x's own close faces: the
        max and midpoint of the previous ``lookback`` daily closes.
        """
        states = np.zeros_like(bar_closes)
        for j in range(bar_closes.shape[1]):
            channel = self._signal.channel(daily_closes[:, j], self._lookback)
            upper = np.repeat(channel.upper, per_day)
            exit_ = np.repeat(
                self._signal.exit_level(channel.upper, channel.lower), per_day
            )
            price = bar_closes[:, j]
            current = 0.0
            for b in range(len(price)):
                # NaN levels or prices compare False and leave the state alone.
                if price[b] > upper[b]:
                    current = 1.0
                elif price[b] < exit_[b]:
                    current = 0.0
                states[b, j] = current
        return states
