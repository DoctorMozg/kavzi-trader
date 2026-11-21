from decimal import Decimal

import numpy as np
import pytest

from kavzi_trader.orchestrator.loops.decision_publisher import DecisionPublisher
from kavzi_trader.orchestrator.loops.decision_queue import DECISION_QUEUE_KEY
from kavzi_trader.orchestrator.loops.strategy import StrategyLoop
from kavzi_trader.strategies.trend.trend_following_config import (
    TrendFollowingConfigSchema,
)
from kavzi_trader.strategies.trend.trend_following_plugin import TrendFollowingPlugin
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore
from tests.spine.execution.rebalance_rig import Rig
from tests.strategies.trend.fake_daily_bars import FakeDailyBars

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
EQUITY = Decimal(1000)
PRICE = Decimal(100)


def _closes() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(3)
    noise = rng.normal(0.0, 0.01, (100, 3))
    drift = np.array([0.004, 0.003, -0.004])
    return {
        s: 100 * np.exp((noise[:, i] + drift[i]).cumsum())
        for i, s in enumerate(SYMBOLS)
    }


@pytest.fixture
async def rig() -> Rig:
    rig = Rig(symbols=tuple(SYMBOLS))
    await rig.state.reset_for_paper(EQUITY)
    return rig


async def test_trend_intents_open_expected_positions(rig: Rig) -> None:
    bars = FakeDailyBars(_closes())
    bars.upto = 99
    plugin = TrendFollowingPlugin(
        TrendFollowingConfigSchema(symbols=SYMBOLS, check_hours=24),
        bars,
        TrendStateStore(rig.redis_client),
    )
    loop = StrategyLoop(plugin, DecisionPublisher(rig.redis_client), clock=rig.clock)

    await loop.step()
    await plugin.flush()

    assert len(rig.redis.lists[DECISION_QUEUE_KEY]) == 2
    assert await rig.loop.step() == 2

    opened = {}
    for symbol in SYMBOLS:
        position = await rig.state.get_position(symbol)
        if position is not None:
            opened[symbol] = position
    assert set(opened) == {"BTCUSDT", "ETHUSDT"}
    stored = await TrendStateStore(rig.redis_client).load()
    for symbol, position in opened.items():
        weight = Decimal(repr(stored.weights[symbol]))
        expected = (weight * EQUITY / PRICE).quantize(
            Decimal("0.00000001"), rounding="ROUND_DOWN"
        )
        assert position.quantity == expected
        assert position.strategy == "trend_following"
        assert position.exit_policy == "SIGNAL"
    assert "SOLUSDT" not in stored.weights
