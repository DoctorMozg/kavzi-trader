import numpy as np
import pytest

from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.strategies.tick_schema import StrategyTickSchema
from kavzi_trader.strategies.trend.trend_following_config import (
    TrendFollowingConfigSchema,
)
from kavzi_trader.strategies.trend.trend_following_plugin import (
    DAY_MS,
    TrendFollowingPlugin,
)
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore
from tests.strategies.trend.fake_daily_bars import FakeDailyBars

BASE_MS = 20_000 * DAY_MS
SYMBOLS = ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"]
FIRST_DAY = 50


def tick_at(day: int) -> StrategyTickSchema:
    return StrategyTickSchema(now_ms=BASE_MS + day * DAY_MS + 60_000)


@pytest.fixture
def config() -> TrendFollowingConfigSchema:
    return TrendFollowingConfigSchema(symbols=SYMBOLS)


@pytest.fixture
def closes() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(7)
    steps = rng.normal(0.0, 0.025, (160, len(SYMBOLS)))
    steps += np.array([0.004, -0.001, 0.002, 0.0])
    return {s: 100 * np.exp(steps[:, i].cumsum()) for i, s in enumerate(SYMBOLS)}


@pytest.fixture
def bars(closes: dict[str, np.ndarray]) -> FakeDailyBars:
    return FakeDailyBars(closes)


def new_store() -> TrendStateStore:
    return TrendStateStore(RedisStateClient.in_memory())


@pytest.fixture
def store() -> TrendStateStore:
    return new_store()


@pytest.fixture
def plugin(
    config: TrendFollowingConfigSchema, bars: FakeDailyBars, store: TrendStateStore
) -> TrendFollowingPlugin:
    return TrendFollowingPlugin(config, bars, store)
