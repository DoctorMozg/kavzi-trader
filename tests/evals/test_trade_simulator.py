from pathlib import Path

import pytest

from kavzi_trader.evals.barrier_enums import BarrierOutcome
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.sim_trade_schema import SimTradeSchema
from kavzi_trader.evals.trade_simulator import TradeSimulator
from kavzi_trader.evals.trader_record_schema import TraderRecordSchema
from tests.evals.eval_fixtures import write_cache
from tests.evals.report_fixtures import (
    DECISION,
    case_for,
    flat_frame,
    joined,
    trader_record,
)

HORIZON = 96


class Scenario:
    """Flat candles in a tmp cache; tests poke bars, then simulate one trade."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.frame = flat_frame()

    def touch(self, bar: int, **values: float) -> None:
        """Set columns of the bar ``bar`` candles after the decision."""
        for column, value in values.items():
            self.frame.loc[DECISION + bar, column] = value

    def run(
        self, record: TraderRecordSchema, label: str = "LONG"
    ) -> SimTradeSchema | None:
        write_cache(self.cache_dir, self.frame)
        case = case_for(self.frame, label)
        simulator = TradeSimulator(CandleCache(self.cache_dir, "15m"))
        return simulator.simulate(joined(case, "trader", record))


@pytest.fixture
def scenario(tmp_path: Path) -> Scenario:
    return Scenario(tmp_path)


class TestTradeSimulator:
    def test_long_take_profit_pays_the_reward_to_risk(self, scenario: Scenario) -> None:
        scenario.touch(2, high=104.5)

        trade = scenario.run(trader_record("LONG", sl=98, tp=104))

        assert trade is not None
        assert trade.outcome is BarrierOutcome.TP
        assert trade.r_multiple == 2.0

    def test_short_stop_loss_costs_one_r(self, scenario: Scenario) -> None:
        scenario.touch(1, high=102.5)

        trade = scenario.run(trader_record("SHORT", sl=102, tp=96), label="SHORT")

        assert trade is not None
        assert trade.outcome is BarrierOutcome.SL
        assert trade.r_multiple == -1.0

    def test_same_bar_stop_and_target_counts_as_stop(self, scenario: Scenario) -> None:
        scenario.touch(1, high=105, low=97)

        trade = scenario.run(trader_record("LONG", sl=98, tp=104))

        assert trade is not None
        assert trade.outcome is BarrierOutcome.SL
        assert trade.r_multiple == -1.0

    def test_timeout_is_marked_to_market_at_the_horizon(
        self, scenario: Scenario
    ) -> None:
        scenario.touch(HORIZON, high=101.0, close=101.0)

        trade = scenario.run(trader_record("LONG", sl=98, tp=104))

        assert trade is not None
        assert trade.outcome is BarrierOutcome.TIMEOUT
        assert trade.r_multiple == pytest.approx(0.5)

    def test_no_valid_trade_is_not_simulated(self, scenario: Scenario) -> None:
        assert scenario.run(trader_record("WAIT", sl=None, tp=None)) is None

    def test_missing_cache_fails_with_the_symbol(self, scenario: Scenario) -> None:
        case = case_for(scenario.frame)
        simulator = TradeSimulator(CandleCache(scenario.cache_dir, "15m"))
        with pytest.raises(FileNotFoundError, match="BTCUSDT"):
            simulator.simulate(joined(case, "trader", trader_record("LONG")))
