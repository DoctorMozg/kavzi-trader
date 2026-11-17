import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.sma_filter_signal import SmaFilterSignal
from kavzi_trader.evals.vol_managed_hold_signal import VolManagedHoldSignal
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema


@pytest.fixture
def closes() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    walks = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.03, (120, 2)), axis=0))
    days = pd.date_range("2024-01-01", periods=120, freq="D")
    return pd.DataFrame(walks, index=days, columns=["BTCUSDT", "ETHUSDT"])


class TestVolManagedHold:
    def test_is_the_trend_sizing_with_the_signal_always_long(
        self, closes: pd.DataFrame
    ) -> None:
        params = TrendParamsSchema()
        sizer = DonchianTrendSignal(params)

        weights = VolManagedHoldSignal(params).weights(closes)

        expected = sizer.vol_scale(closes["ETHUSDT"].to_numpy()) / 2
        np.testing.assert_allclose(weights[:, 1], expected)
        warm = params.vol_window + 1
        assert (weights[:warm] == 0).sum() > 0
        assert (weights[warm:] > 0).all()


class TestSmaFilter:
    def test_long_above_the_average_flat_below_and_during_warmup(self) -> None:
        closes = pd.DataFrame({"BTCUSDT": [10.0, 10, 10, 13, 12, 7, 9]})

        weights = SmaFilterSignal(3).weights(closes)

        assert weights[:, 0].tolist() == [0, 0, 0, 1, 1, 0, 0]

    def test_weight_uses_no_later_close(self, closes: pd.DataFrame) -> None:
        signal = SmaFilterSignal(20)
        shocked = closes.copy()
        shocked.iloc[80:] *= 3.0

        np.testing.assert_array_equal(
            signal.weights(closes)[:80], signal.weights(shocked)[:80]
        )

    def test_splits_the_book_across_symbols(self, closes: pd.DataFrame) -> None:
        weights = SmaFilterSignal(20).weights(closes)

        assert set(np.unique(weights)) <= {0.0, 0.5}

    def test_rejects_a_window_below_two(self) -> None:
        with pytest.raises(ValueError, match="window must be at least 2"):
            SmaFilterSignal(1)
