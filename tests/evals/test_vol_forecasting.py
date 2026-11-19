import numpy as np
import pandas as pd
import pytest
import torch

from kavzi_trader.cli.commands.vol_forecast import pick_winner
from kavzi_trader.evals import chronos_vol_forecaster
from kavzi_trader.evals.chronos_vol_forecaster import ChronosVolForecaster
from kavzi_trader.evals.forecast_vol_trend_signal import ForecastVolTrendSignal
from kavzi_trader.evals.har_vol_forecaster import HarVolForecaster
from kavzi_trader.evals.lgbm_vol_forecaster import LgbmVolForecaster
from kavzi_trader.evals.realized_variance import RealizedVariance
from kavzi_trader.evals.rolling_vol_forecaster import RollingVolForecaster
from kavzi_trader.evals.vol_forecast_evaluator import VolForecastEvaluator
from kavzi_trader.evals.vol_forecast_score_schema import VolForecastScoreSchema
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema

DAYS = pd.date_range("2021-01-01", periods=900, freq="D")
FIRST = pd.Timestamp("2022-06-01")


@pytest.fixture
def returns() -> pd.DataFrame:
    """GARCH(1,1) returns: vol clusters, so recent variance predicts the next week."""
    rng = np.random.default_rng(3)
    out = {}
    for symbol in ("A", "B"):
        var, r = np.empty(len(DAYS)), np.empty(len(DAYS))
        var[0] = 0.0016
        for t in range(len(DAYS)):
            if t:
                var[t] = 2e-5 + 0.12 * r[t - 1] ** 2 + 0.86 * var[t - 1]
            r[t] = np.sqrt(var[t]) * rng.standard_normal()
        out[symbol] = r
    frame = pd.DataFrame(out, index=DAYS)
    frame.iloc[0] = np.nan
    return frame


def _closes(returns: pd.DataFrame) -> pd.DataFrame:
    return 100 * np.exp(returns.fillna(0).cumsum())


class TestRealizedVariance:
    def test_forward_target_is_the_backward_variance_seven_days_later(
        self, returns: pd.DataFrame
    ) -> None:
        forward = RealizedVariance.forward(returns)
        backward = RealizedVariance.backward(returns, 7)

        assert forward.iloc[100, 0] == backward.iloc[107, 0]
        assert forward.iloc[-7:].isna().all().all()


class TestForecastersUseOnlyThePast:
    @pytest.mark.parametrize(
        "make",
        [lambda: HarVolForecaster(FIRST), lambda: LgbmVolForecaster(FIRST)],
        ids=["har", "lgbm"],
    )
    def test_changing_the_future_leaves_earlier_forecasts_alone(
        self, returns: pd.DataFrame, make: object
    ) -> None:
        cut = pd.Timestamp("2022-09-15")
        shocked = returns.copy()
        shocked.loc[shocked.index > cut] *= 5

        plain = make().forecast(returns)  # type: ignore[operator]
        changed = make().forecast(shocked)  # type: ignore[operator]

        # September is fit on targets that ended before 2022-09-01.
        through = plain.index <= cut
        pd.testing.assert_frame_equal(plain[through], changed[through])

    def test_har_beats_a_stale_estimate_on_clustered_vol(
        self, returns: pd.DataFrame
    ) -> None:
        realized = RealizedVariance.forward(returns)
        days = returns.index[(returns.index >= FIRST) & realized.notna().all(axis=1)]
        evaluator = VolForecastEvaluator(realized, days)
        stale = RollingVolForecaster(120)

        score = evaluator.score(
            HarVolForecaster(FIRST).forecast(returns),
            stale.forecast(returns),
            "har",
            stale.name,
        )

        assert score.mean_qlike < score.baseline_qlike
        assert score.dm_stat is not None
        assert score.dm_stat > 0


class _EchoPipeline:
    """Predicts that log RV7 stays at its last value."""

    def predict_quantiles(
        self, contexts: list[torch.Tensor], **_: object
    ) -> tuple[list[torch.Tensor], list[torch.Tensor]]:
        quantiles = [c[-1].repeat(1, 7, 1) for c in contexts]
        return quantiles, []


class TestChronosVolForecaster:
    def test_feeds_each_close_its_own_history_and_reads_step_seven(
        self, returns: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            chronos_vol_forecaster.BaseChronosPipeline,
            "from_pretrained",
            lambda *_, **__: _EchoPipeline(),
        )

        forecast = ChronosVolForecaster(FIRST, revision="test").forecast(returns)

        backward = RealizedVariance.backward(returns, 7)
        scored = forecast.index >= FIRST
        np.testing.assert_allclose(forecast[scored], backward[scored], rtol=1e-5)
        assert forecast[~scored].isna().all().all()


class TestVolForecastEvaluator:
    def test_perfect_forecast_has_zero_loss(self, returns: pd.DataFrame) -> None:
        realized = RealizedVariance.forward(returns)
        days = returns.index[realized.notna().all(axis=1)]
        noise = np.exp(np.random.default_rng(4).normal(0, 0.5, realized.shape))

        score = VolForecastEvaluator(realized, days).score(
            realized, realized * noise, "oracle", "noisy"
        )

        assert score.mean_qlike == pytest.approx(0)
        assert score.baseline_qlike > 0
        assert score.p_value is not None
        assert score.p_value < 0.001


class TestForecastVolTrendSignal:
    def test_rolling_forecast_reproduces_the_paper_rule(
        self, returns: pd.DataFrame
    ) -> None:
        closes = _closes(returns)
        params = TrendParamsSchema(lookbacks=(20,))
        variance = RollingVolForecaster(params.vol_window).forecast(
            RealizedVariance.log_returns(closes)
        )

        np.testing.assert_allclose(
            ForecastVolTrendSignal(params, variance).weights(closes),
            DonchianTrendSignal(params).weights(closes),
        )


def _score(name: str, qlike: float, p: float) -> VolForecastScoreSchema:
    return VolForecastScoreSchema(
        name=name,
        symbols=["A"],
        days=100,
        mean_qlike=qlike,
        baseline="rolling-30d",
        baseline_qlike=1.0,
        dm_stat=2.0,
        p_value=p,
    )


class TestPickWinner:
    def test_lowest_loss_significant_candidate_wins(self) -> None:
        scores = [
            _score("har", 0.9, 0.01),
            _score("lgbm", 0.8, 0.2),
            _score("chronos-2", 0.85, 0.04),
            _score("har-dvol", 0.5, 0.001),
        ]

        winner = pick_winner(scores)

        assert winner is not None
        assert winner.name == "chronos-2"

    def test_no_significant_candidate_means_no_trading_test(self) -> None:
        assert pick_winner([_score("har", 0.9, 0.3)]) is None
