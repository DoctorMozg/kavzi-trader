import numpy as np
import pandas as pd
import pytest

from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.weight_backtest import WeightBacktest
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

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
def backtest() -> WeightBacktest:
    return WeightBacktest(
        DonchianTrendSignal(TrendParamsSchema(lookbacks=(20,))),
        TurnoverBuffer(0.2),
        TrendPortfolio(0.0005),
    )


class TestWeightBacktestWindow:
    def test_scores_only_return_days_inside_the_window(
        self, data: TrendDataSchema, backtest: WeightBacktest
    ) -> None:
        result = backtest.run(
            data, pd.Timestamp("2027-03-01"), pd.Timestamp("2027-05-31")
        )

        assert result.first_day == "2027-03-01"
        assert result.last_day == "2027-05-31"
        assert result.days == 92

    def test_empty_window_is_an_error(
        self, data: TrendDataSchema, backtest: WeightBacktest
    ) -> None:
        with pytest.raises(ValueError, match="no return days"):
            backtest.run(data, pd.Timestamp("2030-01-01"), pd.Timestamp("2030-02-01"))


class ConstantWeights:
    """Holds the same weights every day."""

    def __init__(self, row: list[float]) -> None:
        self._row = np.array(row)

    def weights(self, closes: pd.DataFrame) -> np.ndarray:
        return np.tile(self._row, (len(closes), 1))


class TestAnyWeightSignal:
    def test_constant_book_earns_its_weighted_returns_less_one_entry_fee(
        self, data: TrendDataSchema
    ) -> None:
        backtest = WeightBacktest(
            ConstantWeights([0.5, -0.25]), TurnoverBuffer(0.0), TrendPortfolio(0.001)
        )

        result = backtest.run(
            data, pd.Timestamp("2027-02-01"), pd.Timestamp("2027-02-03")
        )

        returns = data.closes.pct_change().loc["2027-02-01":"2027-02-03"]
        funding = 0.0001 * (0.5 - 0.25)
        daily = returns @ np.array([0.5, -0.25]) - funding
        daily.iloc[0] -= 0.001 * 0.75
        assert result.days == 3
        assert result.net.annual_vol == pytest.approx(daily.std() * np.sqrt(365))
        growth = (1 + daily).prod() ** (365 / 3) - 1
        assert result.net.annual_return == pytest.approx(growth)

    def test_weights_of_the_wrong_shape_are_rejected(
        self, data: TrendDataSchema
    ) -> None:
        backtest = WeightBacktest(
            ConstantWeights([1.0]), TurnoverBuffer(0.0), TrendPortfolio(0.0)
        )

        with pytest.raises(ValueError, match="weights"):
            backtest.run(data)


class TestDelistedSymbol:
    def test_a_delisted_symbol_goes_flat_and_earns_nothing_after(
        self, data: TrendDataSchema
    ) -> None:
        closes = data.closes.copy()
        closes.loc["2027-02-11":, "B"] = np.nan
        funding = data.funding.copy()
        gone = TrendDataSchema(closes=closes, funding=funding)
        backtest = WeightBacktest(
            ConstantWeights([0.5, 0.5]), TurnoverBuffer(0.0), TrendPortfolio(0.0)
        )

        result = backtest.run(
            gone, pd.Timestamp("2027-02-05"), pd.Timestamp("2027-02-20")
        )

        net = pd.Series(
            result.daily_net, index=pd.date_range("2027-02-05", "2027-02-20")
        )
        a_only = 0.5 * closes["A"].pct_change() - 0.5 * 0.0001
        # B's last close is Feb 10, so from Feb 11 only A's half earns or pays.
        np.testing.assert_allclose(
            net["2027-02-11":], a_only["2027-02-11":"2027-02-20"]
        )
        assert result.benchmark.sharpe is not None
        assert np.isfinite(result.benchmark.sharpe)


def test_donchian_weights_split_the_book_across_symbols(
    data: TrendDataSchema,
) -> None:
    signal = DonchianTrendSignal(TrendParamsSchema(lookbacks=(20,)))

    weights = signal.weights(data.closes)

    alone = signal.compute(data.closes["A"].to_numpy(), 2).weight
    np.testing.assert_array_equal(weights[:, 0], alone)
