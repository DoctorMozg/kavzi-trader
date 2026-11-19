import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.funding_crowding_overlay import FundingCrowdingOverlay

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
