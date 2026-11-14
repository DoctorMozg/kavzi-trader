from decimal import Decimal

import pandas as pd
import pytest

from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.evals.market_feature_builder import (
    ATR_HISTORY_WINDOW,
    REGIME_ORDER,
    MarketFeatureBuilder,
)
from kavzi_trader.indicators.volatility import calculate_atr
from kavzi_trader.orchestrator.providers.market_data_cache import ATR_HISTORY_LENGTH
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from tests.evals.frames import make_frame


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    # Volatility doubles midway so every regime shows up.
    calm = make_frame(400, seed=1, drift_vol=0.001)
    wild = make_frame(
        300,
        seed=2,
        drift_vol=0.01,
        start_ms=int(calm["open_time_ms"].iloc[-1]) + 900_000,
    )
    return pd.concat([calm, wild], ignore_index=True)


@pytest.fixture(scope="module")
def risk() -> RiskConfigSchema:
    return RiskConfigSchema()


class TestMarketFeatureBuilder:
    def test_window_matches_live_cache(self) -> None:
        assert ATR_HISTORY_WINDOW == ATR_HISTORY_LENGTH

    def test_atr_matches_live_indicator(
        self, frame: pd.DataFrame, risk: RiskConfigSchema
    ) -> None:
        features = MarketFeatureBuilder(risk).build(frame)
        for i in (14, 60, 399, 650):
            window = frame.iloc[: i + 1]
            expected = calculate_atr(window["high"], window["low"], window["close"], 14)
            assert expected is not None
            assert features.atr[i] == pytest.approx(float(expected), rel=1e-6)

    def test_regime_matches_live_detector(
        self, frame: pd.DataFrame, risk: RiskConfigSchema
    ) -> None:
        features = MarketFeatureBuilder(risk).build(frame)
        detector = VolatilityRegimeDetector(risk)
        seen = set()
        for i in range(ATR_HISTORY_WINDOW + 14, len(frame)):
            history = [
                Decimal(str(round(a, 8)))
                for a in features.atr[i - ATR_HISTORY_WINDOW + 1 : i + 1]
            ]
            live = detector.detect_regime(history[-1], history).regime
            assert REGIME_ORDER[features.regime_code[i]] is live, i
            seen.add(live)
        assert len(seen) >= 3
