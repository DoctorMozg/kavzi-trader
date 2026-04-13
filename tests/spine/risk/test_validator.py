from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)


def make_position(symbol: str) -> PositionSchema:
    return PositionSchema(
        id="pos-1",
        symbol=symbol,
        side="LONG",
        quantity=Decimal("0.1"),
        entry_price=Decimal(50000),
        stop_loss=Decimal(49000),
        take_profit=Decimal(52000),
        current_stop_loss=Decimal(49000),
        management_config=PositionManagementConfigSchema(),
        opened_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestDynamicRiskValidator:
    @pytest.mark.asyncio
    async def test_valid_trade_passes(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        atr_history = [Decimal(100)] * 10

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=atr_history,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is True
        assert result.rejection_reasons == []
        assert result.volatility_regime == VolatilityRegime.NORMAL

    @pytest.mark.asyncio
    async def test_rejects_high_drawdown(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        mock_state_manager.get_current_drawdown = AsyncMock(return_value=Decimal("4.0"))

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("drawdown" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_close_all_triggered_at_5_percent(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        mock_state_manager.get_current_drawdown = AsyncMock(return_value=Decimal("6.0"))

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert result.should_close_all is True

    @pytest.mark.asyncio
    async def test_rejects_max_positions(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        mock_state_manager.get_all_positions = AsyncMock(
            return_value=[make_position("BTCUSDT"), make_position("ETHUSDT")],
        )

        result = await validator.validate_trade(
            symbol="SOLUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("max positions" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_rejects_extreme_volatility(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        atr_history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(120),
            atr_history=atr_history,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert result.volatility_regime == VolatilityRegime.EXTREME

    @pytest.mark.asyncio
    async def test_rejects_low_volatility(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        atr_history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(92),
            atr_history=atr_history,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert result.volatility_regime == VolatilityRegime.LOW

    @pytest.mark.asyncio
    async def test_rejects_stop_loss_too_tight(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49990),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("too tight" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_rejects_stop_loss_too_wide(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49500),
            take_profit=Decimal(52000),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("too wide" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_rejects_stop_loss_below_min_percent(
        self, mock_state_manager
    ) -> None:
        """LTCUSDT scenario: SL passes ATR check but is only 0.055% of entry."""
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="LTCUSDT",
            side="LONG",
            entry_price=Decimal("54.14"),
            stop_loss=Decimal("54.11"),
            take_profit=Decimal("54.72"),
            current_atr=Decimal("0.06"),
            atr_history=[Decimal("0.06")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any(
            "too tight" in r.lower() and "%" in r for r in result.rejection_reasons
        )

    @pytest.mark.asyncio
    async def test_sl_percent_floor_passes_normal_trade(
        self, mock_state_manager
    ) -> None:
        """Normal trade with adequate SL distance passes both ATR and % checks."""
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_rejects_poor_risk_reward(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50050),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("r:r ratio" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_rejects_long_with_sl_above_entry(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(50100),
            take_profit=Decimal(51000),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("below entry" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_rejects_short_with_sl_below_entry(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="SHORT",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(49000),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("above entry" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_high_volatility_warning(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        atr_history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(105),
            atr_history=atr_history,
            state_manager=mock_state_manager,
        )

        assert result.volatility_regime == VolatilityRegime.HIGH
        assert any("high volatility" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_calculates_recommended_size(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        mock_state_manager.get_account_state = AsyncMock(
            return_value=AccountStateSchema(
                total_balance_usdt=Decimal(10000),
                available_balance_usdt=Decimal(10000),
                locked_balance_usdt=Decimal(0),
                peak_balance=Decimal(10000),
                updated_at=datetime.now(UTC),
            ),
        )

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is True
        assert result.recommended_size > Decimal(0)

    @pytest.mark.asyncio
    async def test_rejects_below_min_notional_floor(self, mock_state_manager) -> None:
        """Account too small to afford the $10 floor → trade rejected cleanly."""
        from kavzi_trader.spine.risk.config import RiskConfigSchema

        # Tiny balance + 1% cap forces max notional below the $10 floor.
        config = RiskConfigSchema(
            max_notional_percent=Decimal("1.0"),
            min_position_notional_usd=Decimal("10.0"),
        )
        validator = DynamicRiskValidator(config)
        mock_state_manager.get_account_state = AsyncMock(
            return_value=AccountStateSchema(
                total_balance_usdt=Decimal(100),
                available_balance_usdt=Decimal(100),
                locked_balance_usdt=Decimal(0),
                peak_balance=Decimal(100),
                updated_at=datetime.now(UTC),
            ),
        )

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert result.recommended_size == Decimal(0)
        assert any("below minimum" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_accepts_when_floor_bump_keeps_size_valid(
        self, mock_state_manager, mock_liquidation_calculator
    ) -> None:
        """Below-floor risk sizing is bumped up to $10 and trade stays valid."""
        from kavzi_trader.spine.risk.config import RiskConfigSchema

        # Risk-based size is microscopic; cap/margin allow floor to be met.
        config = RiskConfigSchema(
            risk_per_trade_percent=Decimal("0.01"),
            max_notional_percent=Decimal("50.0"),
            min_position_notional_usd=Decimal("10.0"),
        )
        validator = DynamicRiskValidator(
            config,
            liquidation_calculator=mock_liquidation_calculator,
        )
        mock_state_manager.get_account_state = AsyncMock(
            return_value=AccountStateSchema(
                total_balance_usdt=Decimal(100),
                available_balance_usdt=Decimal(100),
                locked_balance_usdt=Decimal(0),
                peak_balance=Decimal(100),
                updated_at=datetime.now(UTC),
            ),
        )

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
            leverage=5,
        )

        assert result.is_valid is True
        assert result.recommended_size * Decimal(50000) >= Decimal("10.0")

    @pytest.mark.asyncio
    async def test_leverage_forwarded_to_position_sizer(
        self, mock_state_manager, mock_liquidation_calculator
    ) -> None:
        validator = DynamicRiskValidator(
            liquidation_calculator=mock_liquidation_calculator,
        )

        result_lev1 = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
            leverage=1,
        )
        result_lev3 = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
            leverage=3,
        )

        assert result_lev1.is_valid is True
        assert result_lev3.is_valid is True
        assert result_lev3.recommended_size >= result_lev1.recommended_size

    @pytest.mark.asyncio
    async def test_rejects_leveraged_trade_without_liquidation_calculator(
        self, mock_state_manager
    ) -> None:
        """No MMR source = no trust; leveraged trade must be rejected."""
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
            leverage=5,
        )

        assert result.is_valid is False
        assert any(
            "liquidation check unavailable" in r.lower()
            for r in result.rejection_reasons
        )

    @pytest.mark.asyncio
    async def test_rejects_when_liquidation_calculator_returns_none(
        self, mock_state_manager
    ) -> None:
        """Transient API failure must not be waved through as 'safe'."""
        calc = MagicMock(spec=LiquidationCalculator)
        calc.estimate_liquidation_price = AsyncMock(return_value=None)
        validator = DynamicRiskValidator(liquidation_calculator=calc)

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
            leverage=5,
        )

        assert result.is_valid is False
        assert any(
            "liquidation price unavailable" in r.lower()
            for r in result.rejection_reasons
        )

    @pytest.mark.asyncio
    async def test_rejects_sl_past_real_liquidation_with_mmr(
        self, mock_state_manager
    ) -> None:
        """Regression: naive formula waved SL past the real liq; MMR rejects.

        Entry 50000, leverage 10, MMR 0.5% puts real liq at
        50000 * (1 - 0.1 + 0.005) = 45250. An SL at 45000 sits BELOW the real
        liquidation and must be rejected; the naive (MMR=0) formula placed
        liq at 45000 and would have approved this SL.
        """
        calc = MagicMock(spec=LiquidationCalculator)
        calc.estimate_liquidation_price = AsyncMock(return_value=Decimal(45250))
        validator = DynamicRiskValidator(liquidation_calculator=calc)

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(45000),
            take_profit=Decimal(60000),
            current_atr=Decimal(2000),
            atr_history=[Decimal(2000)] * 10,
            state_manager=mock_state_manager,
            leverage=10,
        )

        assert result.is_valid is False
        assert any("liquidation" in r.lower() for r in result.rejection_reasons)
