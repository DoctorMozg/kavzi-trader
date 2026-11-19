import numpy as np
import pytest

from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema


class TestMidExitTrendSignal:
    def test_exits_at_midpoint_where_the_donchian_rule_still_holds(self) -> None:
        params = TrendParamsSchema(lookbacks=(5,))
        rise = list(np.linspace(100, 110, 10))
        # Prior 5 closes span 105.6-110: 106 is below their midpoint, above their low.
        close = np.array([*rise, 106.0])

        mid = MidExitTrendSignal(params).compute(close, 1).signal
        donchian = DonchianTrendSignal(params).compute(close, 1).signal

        assert mid[9] == donchian[9] == 1
        assert mid[10] == 0
        assert donchian[10] == 1

    def test_long_short_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="long/flat"):
            MidExitTrendSignal(TrendParamsSchema(long_short=True))

    def test_exit_level_is_the_channel_midpoint(self) -> None:
        signal = MidExitTrendSignal(TrendParamsSchema())

        assert signal.exit_level(110.0, 100.0) == 105.0
        np.testing.assert_array_equal(
            signal.exit_level(np.array([10.0, 20.0]), np.array([0.0, 10.0])),
            np.array([5.0, 15.0]),
        )
        assert (
            DonchianTrendSignal(TrendParamsSchema()).exit_level(110.0, 100.0) == 100.0
        )
