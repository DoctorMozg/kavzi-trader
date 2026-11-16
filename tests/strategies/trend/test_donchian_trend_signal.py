import numpy as np
import pytest

from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema

CLOSES = np.array([10.0, 11, 12, 13, 12, 9, 10, 14])
# Target so high that the leverage cap (2.0) always binds once vol is defined.
CAPPED = {"annual_vol_target": 1e6, "vol_window": 2}


def _signal(lookbacks: tuple[int, ...], **extra: object) -> DonchianTrendSignal:
    params = TrendParamsSchema.model_validate(
        {"lookbacks": lookbacks, **CAPPED, **extra}
    )
    return DonchianTrendSignal(params)


@pytest.fixture
def random_walk() -> np.ndarray:
    rng = np.random.default_rng(7)
    return 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))


class TestStateMachine:
    def test_breakout_holds_inside_channel_and_drops_below_low(self) -> None:
        result = _signal((3,)).compute(CLOSES, n_symbols=1)

        assert result.signal.tolist() == [0, 0, 0, 1, 1, 0, 0, 1]

    def test_long_short_goes_to_minus_one_below_the_low(self) -> None:
        result = _signal((3,), long_short=True).compute(CLOSES, n_symbols=1)

        assert result.signal.tolist() == [0, 0, 0, 1, 1, -1, -1, 1]

    def test_touching_the_channel_edge_is_not_a_breakout(self) -> None:
        flat_then_equal = np.array([10.0, 11, 12, 12, 12])

        result = _signal((2,)).compute(flat_then_equal, n_symbols=1)

        assert result.signal.tolist() == [0, 0, 1, 1, 1]

    def test_signal_is_mean_of_lookback_states(self) -> None:
        result = _signal((2, 3)).compute(CLOSES, n_symbols=1)

        assert result.signal.tolist() == [0, 0, 0.5, 1, 1, 0, 0, 1]


class TestWeight:
    def test_weight_is_capped_scale_over_symbol_count(self) -> None:
        result = _signal((2, 3)).compute(CLOSES, n_symbols=4)

        assert result.weight[2] == pytest.approx(0.5 * 2.0 / 4)
        assert result.weight[3] == pytest.approx(1.0 * 2.0 / 4)

    def test_weight_is_zero_while_vol_window_warms_up(self) -> None:
        result = _signal((1,)).compute(CLOSES, n_symbols=1)

        assert result.weight[:2].tolist() == [0.0, 0.0]

    def test_weight_targets_annual_vol(self) -> None:
        closes = np.exp(np.array([0.0, -0.01, 0.0]))
        params = TrendParamsSchema(lookbacks=(1,), vol_window=2)

        result = DonchianTrendSignal(params).compute(closes, n_symbols=2)

        vol = np.std([-0.01, 0.01], ddof=1) * np.sqrt(365)
        assert result.weight[2] == pytest.approx(0.25 / vol / 2)

    def test_rejects_non_positive_symbol_count(self) -> None:
        with pytest.raises(ValueError, match="n_symbols"):
            _signal((3,)).compute(CLOSES, n_symbols=0)


class TestNoLookAhead:
    def test_value_at_t_ignores_later_closes(self, random_walk: np.ndarray) -> None:
        signal = DonchianTrendSignal(TrendParamsSchema())
        full = signal.compute(random_walk, n_symbols=8)

        for k in (100, 150, 299):
            truncated = signal.compute(random_walk[: k + 1], n_symbols=8)
            assert truncated.signal[k] == full.signal[k]
            assert truncated.weight[k] == pytest.approx(full.weight[k])

    def test_rewriting_the_future_leaves_the_past_unchanged(
        self, random_walk: np.ndarray
    ) -> None:
        signal = DonchianTrendSignal(TrendParamsSchema())
        altered = random_walk.copy()
        altered[200:] *= np.linspace(1.0, 3.0, 100)

        before = signal.compute(random_walk, n_symbols=8)
        after = signal.compute(altered, n_symbols=8)

        np.testing.assert_array_equal(before.signal[:200], after.signal[:200])
        np.testing.assert_allclose(before.weight[:200], after.weight[:200])
