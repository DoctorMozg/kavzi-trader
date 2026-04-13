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
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        config = RiskConfigSchema(max_notional_percent=Decimal(999))
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(50000),
            leverage=3,
        )

        assert result.risk_amount == Decimal(100)
        assert result.base_size == Decimal("0.5")
        assert result.adjusted_size == Decimal("0.5")
        assert result.size_multiplier == Decimal("1.0")

    def test_high_regime_reduces_size(
        self,
        high_regime: VolatilityRegimeSchema,
    ) -> None:
        config = RiskConfigSchema(max_notional_percent=Decimal(999))
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=high_regime,
            entry_price=Decimal(50000),
            leverage=3,
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

    def test_notional_cap_applied_before_margin_clamp(
        self,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        """Notional cap should be applied before margin clamp."""
        # ATR-based size would be 100 / 1.0 = 100 units
        # At entry_price=10, notional = 100 * 10 = $1,000
        # With explicit 30% cap on $1,000 balance, max notional = $300 → max size = 30
        # Margin with leverage=10: 1000 * 10 / 10 = 1000 (much larger)
        # So notional cap should be the binding constraint
        config = RiskConfigSchema(max_notional_percent=Decimal("30.0"))
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(1000),
            atr=Decimal("1.0"),
            stop_loss_atr_multiplier=Decimal("1.0"),
            regime=normal_regime,
            entry_price=Decimal(10),
            leverage=10,
        )
        max_notional = Decimal(1000) * Decimal("0.30")
        max_size = max_notional / Decimal(10)
        assert result.adjusted_size <= max_size
        assert result.adjusted_size > Decimal(0)

    def test_notional_cap_clamps_low_price_asset(
        self,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        """DOGEUSDT scenario: ATR sizing produces huge qty on cheap assets."""
        config = RiskConfigSchema(max_notional_percent=Decimal("30.0"))  # explicit
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal("0.00058"),
            stop_loss_atr_multiplier=Decimal("1.0"),
            regime=normal_regime,
            entry_price=Decimal("0.09"),
            leverage=1,
        )
        # Without cap: 100 / 0.00058 = 172,414 DOGE → $15,517 notional (155%)
        # With 30% cap: max notional = $3,000 → 3000 / 0.09 = 33,333 DOGE
        max_notional = Decimal(10000) * Decimal("0.30")
        max_size = max_notional / Decimal("0.09")
        assert result.adjusted_size <= max_size
        assert result.adjusted_size > Decimal(0)

    def test_notional_floor_bumps_tiny_position(
        self,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        """Micro account: risk-based sizing below floor is bumped up to $10."""
        # Risk: 1% of $100 = $1. SL distance = 2 * 100 = 200.
        # Base size = 1 / 200 = 0.005 BTC → $0.005 * 50000 = $250 notional.
        # Wait — that's above floor. Need a scenario where notional < floor.
        # With entry=50000, atr=10, sl_mult=1: stop_distance=10, base=1/10=0.1 BTC
        # → notional = 0.1 * 50000 = $5000. Still above floor.
        # Use tiny risk: balance=$100, risk=0.01%, stop=2 * 100 = 200,
        # risk_amount = $0.01, base = 0.01/200 = 0.00005 BTC → $2.5 notional.
        config = RiskConfigSchema(
            risk_per_trade_percent=Decimal("0.01"),
            max_notional_percent=Decimal(999),
            min_position_notional_usd=Decimal("10.0"),
        )
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(100),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(50000),
            leverage=5,
            available_balance=Decimal(100),
        )
        # Floor bumps size so notional >= $10
        notional = result.adjusted_size * Decimal(50000)
        assert notional >= Decimal("10.0")

    def test_notional_floor_respects_low_regime_block(self) -> None:
        """LOW regime (size_multiplier=0) must stay at zero, not bump to floor."""
        low_regime = VolatilityRegimeSchema(
            regime=VolatilityRegime.LOW,
            atr_zscore=Decimal("-2.0"),
            size_multiplier=Decimal(0),
            is_tradeable=False,
        )
        config = RiskConfigSchema(min_position_notional_usd=Decimal("10.0"))
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(10000),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=low_regime,
            entry_price=Decimal(50000),
        )
        assert result.adjusted_size == Decimal(0)

    def test_notional_floor_disabled_when_zero(
        self,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        """Setting floor to 0 disables the bump."""
        config = RiskConfigSchema(
            risk_per_trade_percent=Decimal("0.01"),
            max_notional_percent=Decimal(999),
            min_position_notional_usd=Decimal(0),
        )
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(100),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(50000),
            leverage=5,
            available_balance=Decimal(100),
        )
        # No floor enforcement — original tiny size kept.
        # risk=0.01, stop=200, base=0.00005, notional=$2.5
        notional = result.adjusted_size * Decimal(50000)
        assert notional < Decimal("10.0")

    def test_quantize_truncates_toward_zero_beyond_8_places(
        self,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        """>8 decimal digits must truncate (ROUND_DOWN), never round up."""
        # risk_amount = 100 * (1% / 100) = 1; stop_distance = 81 * 1 = 81
        # base_size = 1 / 81 = 0.012345679012345679... (repeating)
        # ROUND_DOWN to 8 places = 0.01234567 (NOT 0.01234568 from banker's)
        config = RiskConfigSchema(max_notional_percent=Decimal(999))
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(100),
            atr=Decimal(81),
            stop_loss_atr_multiplier=Decimal(1),
            regime=normal_regime,
            entry_price=Decimal(50000),
            leverage=100,
        )

        assert result.base_size == Decimal("0.01234567")
        assert result.adjusted_size == Decimal("0.01234567")

    def test_quantize_preserves_exact_decimal_arithmetic(
        self,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        """No float round-trip: banker's-on-float and ROUND_DOWN diverge here."""
        # risk_amount = 500 * (1% / 100) = 5; stop_distance = 7 * 1 = 7
        # base_size = 5 / 7 = 0.714285714285... (9th digit = 7)
        # Old float path: round(float(5/7), 8) rounds up to 0.71428572.
        # New path: Decimal.quantize(..., ROUND_DOWN) truncates to 0.71428571.
        config = RiskConfigSchema(max_notional_percent=Decimal(999))
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(500),
            atr=Decimal(7),
            stop_loss_atr_multiplier=Decimal(1),
            regime=normal_regime,
            entry_price=Decimal(50000),
            leverage=100,
        )

        assert result.base_size == Decimal("0.71428571")
        assert result.risk_amount == Decimal("5.00000000")
        assert result.risk_amount == Decimal(5)

    def test_notional_floor_clipped_by_max_notional_cap(
        self,
        normal_regime: VolatilityRegimeSchema,
    ) -> None:
        """When max notional cap < floor, the cap wins (validator rejects)."""
        # Floor says $10, but max cap is 5% of $100 = $5 → cap wins.
        config = RiskConfigSchema(
            risk_per_trade_percent=Decimal("0.01"),
            max_notional_percent=Decimal("5.0"),
            min_position_notional_usd=Decimal("10.0"),
        )
        sizer = PositionSizer(config)
        result = sizer.calculate_size(
            account_balance=Decimal(100),
            atr=Decimal(100),
            stop_loss_atr_multiplier=Decimal(2),
            regime=normal_regime,
            entry_price=Decimal(50000),
            leverage=5,
            available_balance=Decimal(100),
        )
        notional = result.adjusted_size * Decimal(50000)
        # Cap = 5% of 100 = $5; floor cannot be honoured
        assert notional <= Decimal("5.0")
