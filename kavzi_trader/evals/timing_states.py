import numpy as np

from kavzi_trader.strategies.trend.channel_state_machine import ChannelStateMachine
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal


class TimingStates:
    """Long/flat states of the mid-exit Donchian rule, one per bar close.

    Each state depends on prices known at that bar's close only.
    """

    def __init__(self, signal: MidExitTrendSignal, lookback: int) -> None:
        self._signal = signal
        self._machine = ChannelStateMachine(signal)
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
        bar_days = np.repeat(np.arange(len(daily_closes)), per_day)
        columns = [
            self._machine.states(
                daily_closes[:, j], bar_closes[:, j], bar_days, self._lookback
            )
            for j in range(bar_closes.shape[1])
        ]
        return np.column_stack(columns)
