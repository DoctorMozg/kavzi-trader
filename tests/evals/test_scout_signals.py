import asyncio
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.market_feature_builder import MarketFeatureBuilder
from kavzi_trader.evals.scout_signals import ScoutSignals
from kavzi_trader.evals.signal_sampler import SignalSampler
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from tests.evals.frames import make_frame

LOOSE = "scout_trend_0.8"
STRICT = "scout_trend_1.2"


def _trending(n: int, drift: float) -> pd.DataFrame:
    """Random walk with a steady drift; volume is constant, so vol_ratio is 1."""
    frame = make_frame(n, seed=11)
    factor = np.exp(drift * np.arange(n))
    for column in ("open", "high", "low", "close"):
        frame[column] = frame[column] * factor
    return frame


@pytest.fixture
def scored(app_config: AppConfig) -> pd.DataFrame:
    history = app_config.trading.history_candles
    frame = _trending(history + 150, drift=0.0004)
    samples = SignalSampler(
        MarketFeatureBuilder(app_config.risk), history, 7, OrderFlowCalculator(15)
    ).sample("BTCUSDT", frame, max_horizon=10)
    scout = ScoutSignals(
        app_config, load_tier_registry(), "15m", [Decimal("0.8"), Decimal("1.2")]
    )
    return asyncio.run(scout.add("BTCUSDT", frame, samples))


class TestScoutSignals:
    def test_threshold_decides_trend_calls(self, scored: pd.DataFrame) -> None:
        # vol_ratio is exactly 1 on every bar: 0.8 lets trend calls through,
        # 1.2 rejects them all.
        assert scored[f"LONG_{LOOSE}"].any()
        assert not scored[f"LONG_{STRICT}"].any()
        assert not scored[f"SHORT_{STRICT}"].any()

    def test_side_follows_the_ema_stack(self, scored: pd.DataFrame) -> None:
        for side in ("LONG", "SHORT"):
            fired = scored[f"{side}_{LOOSE}"]
            assert scored.loc[fired, f"{side}_ema_alignment"].all()
        assert not (scored[f"LONG_{LOOSE}"] & scored[f"SHORT_{LOOSE}"]).any()

    def test_names_list_one_signal_per_threshold(self, app_config: AppConfig) -> None:
        scout = ScoutSignals(
            app_config, load_tier_registry(), "15m", [Decimal("0.8"), Decimal("1.2")]
        )
        assert scout.names == [LOOSE, STRICT]
