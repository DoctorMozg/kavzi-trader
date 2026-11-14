from decimal import Decimal

import numpy as np
import pytest

from kavzi_trader.brain.geometry.calculator import TradeGeometryCalculator
from kavzi_trader.brain.geometry.schemas import (
    GeometryInputsSchema,
    GeometryRejectionSchema,
)
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.trade_structure import TradeStructureSchema
from kavzi_trader.evals.bracket_policy import BracketPolicy
from kavzi_trader.evals.market_feature_builder import REGIME_ORDER


class TestBracketPolicy:
    @pytest.mark.parametrize("regime", REGIME_ORDER)
    @pytest.mark.parametrize("atr_pct", [0.05, 0.09, 0.12, 0.3, 1.0])
    def test_matches_geometry_calculator(self, regime, atr_pct: float) -> None:
        risk = RiskConfigSchema()
        policy = BracketPolicy(risk)
        price, atr = 100.0, atr_pct
        out = policy.distances(
            np.array([REGIME_ORDER.index(regime)], dtype=np.int8),
            np.array([atr]),
            np.array([price]),
        )
        geometry = TradeGeometryCalculator(risk).compute(
            TradeStructureSchema(
                direction="LONG",
                stop_atr_multiplier=Decimal(
                    str(policy.nominal_stop_atr()[regime.value])
                ),
                target_style="ATR_2X",
            ),
            GeometryInputsSchema(
                symbol="X", current_price=Decimal(str(price)), atr_14=Decimal(str(atr))
            ),
        )
        if isinstance(geometry, GeometryRejectionSchema):
            assert not out.valid[0]
            return
        assert out.valid[0]
        assert out.sl_distance[0] == pytest.approx(
            float(geometry.entry - geometry.stop_loss)
        )
        assert out.tp_distance[0] == pytest.approx(
            float(geometry.take_profit - geometry.entry)
        )

    def test_every_regime_uses_widest_stop_the_calculator_admits(self) -> None:
        stops = BracketPolicy(RiskConfigSchema()).nominal_stop_atr()
        assert set(stops.values()) == {1.5}
        assert set(stops) == {r.value for r in REGIME_ORDER}
