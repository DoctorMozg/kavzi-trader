from decimal import Decimal

import pytest

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.position_sizer import PositionSizer
from kavzi_trader.spine.risk.schemas import VolatilityRegime, VolatilityRegimeSchema


@pytest.fixture
def normal_regime() -> VolatilityRegimeSchema:
    return VolatilityRegimeSchema(
        regime=VolatilityRegime.NORMAL,
        atr_zscore=Decimal(0),
        size_multiplier=Decimal("1.0"),
        is_tradeable=True,
    )


@pytest.fixture
def high_regime() -> VolatilityRegimeSchema:
    return VolatilityRegimeSchema(
        regime=VolatilityRegime.HIGH,
        atr_zscore=Decimal("1.5"),
        size_multiplier=Decimal("0.5"),
        is_tradeable=True,
    )


class TestPositionSizer:
    def test_basic_position_sizing(
        self,
        risk_config: RiskConfigSchema,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        sizer = PositionSizer(risk_config)
        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(50000),
        )

        assert result.risk_amount == Decimal(100)
        assert result.base_size == Decimal("0.5")
        assert result.adjusted_size == Decimal("0.5")
        assert result.size_multiplier == Decimal("1.0")

    def test_high_regime_reduces_size(
        self,
        risk_config: RiskConfigSchema,
        high_regime: VolatilityRegimeSchema,
    ) -> None:
        sizer = PositionSizer(risk_config)
        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=high_regime,
            entry_price=Decimal(50000),
        )

        assert result.base_size == Decimal("0.5")
        assert result.adjusted_size == Decimal("0.25")
        assert result.size_multiplier == Decimal("0.5")

    def test_zero_atr_returns_zero_size(
        self,
        risk_config: RiskConfigSchema,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        sizer = PositionSizer(risk_config)
        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(0),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(50000),
        )

        assert result.base_size == Decimal(0)
        assert result.adjusted_size == Decimal(0)

    def test_zero_entry_price_returns_zero_size(
        self,
        risk_config: RiskConfigSchema,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        sizer = PositionSizer(risk_config)
        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(0),
        )

        assert result.adjusted_size == Decimal(0)

    def test_larger_atr_multiplier_reduces_size(
        self,
        risk_config: RiskConfigSchema,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        sizer = PositionSizer(risk_config)

        result_2x = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(50000),
        )

        result_4x = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(4),
            regime=normal_regime,
            entry_price=Decimal(50000),
        )

        assert result_4x.base_size == result_2x.base_size / 2

    def test_custom_risk_percent(
        self,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        config = RiskConfigSchema(risk_per_trade_percent=Decimal("2.0"))
        sizer = PositionSizer(config)

        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(50000),
        )

        assert result.risk_amount == Decimal(200)
