import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.evals.trend_backtest import TrendBacktest
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_params_schema import TrendParamsSchema
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.turnover_buffer import TurnoverBuffer

DAYS = pd.date_range("2027-01-01", periods=200, freq="D")


@pytest.fixture
def data() -> TrendDataSchema:
    rng = np.random.default_rng(3)
    steps = rng.normal(0.002, 0.03, size=(len(DAYS), 2))
    closes = pd.DataFrame(
        100 * np.exp(np.cumsum(steps, axis=0)), index=DAYS, columns=["A", "B"]
    )
    funding = pd.DataFrame(0.0001, index=DAYS, columns=["A", "B"])
    return TrendDataSchema(closes=closes, funding=funding)


@pytest.fixture
def backtest() -> TrendBacktest:
    return TrendBacktest(
        DonchianTrendSignal(TrendParamsSchema(lookbacks=(20,))),
        TurnoverBuffer(0.2),
        TrendPortfolio(0.0005),
    )


class TestTrendBacktestWindow:
    def test_scores_only_return_days_inside_the_window(
        self, data: TrendDataSchema, backtest: TrendBacktest
    ) -> None:
        result = backtest.run(
            data, pd.Timestamp("2027-03-01"), pd.Timestamp("2027-05-31")
        )

        assert result.first_day == "2027-03-01"
        assert result.last_day == "2027-05-31"
        assert result.days == 92

    def test_empty_window_is_an_error(
        self, data: TrendDataSchema, backtest: TrendBacktest
    ) -> None:
        with pytest.raises(ValueError, match="no return days"):
            backtest.run(data, pd.Timestamp("2030-01-01"), pd.Timestamp("2030-02-01"))
