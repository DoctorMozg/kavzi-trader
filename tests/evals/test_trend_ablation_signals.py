import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.funding_crowding_overlay import FundingCrowdingOverlay
from kavzi_trader.evals.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema

DAYS = pd.date_range("2022-01-01", periods=400, freq="D")


class _AlwaysLong:
    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        return np.full(closes.shape, 0.5)


@pytest.fixture
def closes() -> pd.DataFrame:
    return pd.DataFrame({"A": np.linspace(100, 200, len(DAYS))}, index=DAYS)


class TestFundingCrowdingOverlay:
    def test_flat_baseline_funding_is_never_crowded(self, closes: pd.DataFrame) -> None:
        funding = pd.DataFrame({"A": 0.0003}, index=DAYS)

        weights = FundingCrowdingOverlay(_AlwaysLong(), funding).weights(closes)

        assert (weights == 0.5).all()

    def test_halves_long_weight_only_on_top_decile_funding_days(
        self, closes: pd.DataFrame
    ) -> None:
        funding = pd.DataFrame({"A": 0.0001}, index=DAYS)
        funding.iloc[300:307, 0] = 0.003

        weights = FundingCrowdingOverlay(_AlwaysLong(), funding).weights(closes)[:, 0]

        assert weights[299] == 0.5
        assert weights[306] == 0.25
        assert set(np.unique(weights)) == {0.25, 0.5}

    def test_passes_weights_through_before_enough_history(
        self, closes: pd.DataFrame
    ) -> None:
        funding = pd.DataFrame({"A": np.linspace(0, 0.01, len(DAYS))}, index=DAYS)

        weights = FundingCrowdingOverlay(_AlwaysLong(), funding).weights(closes)[:, 0]

        # Rising funding is always at its own high, but needs 7 + 179 days first.
        assert (weights[:185] == 0.5).all()
        assert (weights[186:] == 0.25).all()

    def test_flag_uses_no_funding_after_the_close(self, closes: pd.DataFrame) -> None:
        funding = pd.DataFrame({"A": 0.0001}, index=DAYS)
        later = funding.copy()
        later.iloc[350:, 0] = 0.01

        early = FundingCrowdingOverlay(_AlwaysLong(), funding).crowded(DAYS, ["A"])
        spiked = FundingCrowdingOverlay(_AlwaysLong(), later).crowded(DAYS, ["A"])

        assert (early[:350] == spiked[:350]).all()


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
