from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.symbol_tier import SymbolTier, SymbolTierConfigSchema
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)

_EXTREME_ATR_HISTORY = [
    Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
]


def make_tier_registry() -> SymbolTierRegistry:
    """Registry mirroring config/tiers.yaml risk budgets (TIER_1 = 4%)."""
    tier_configs = {
        SymbolTier.TIER_1: SymbolTierConfigSchema.model_validate(
            {
                "risk_per_trade_percent": "4.0",
                "max_leverage": 10,
                "max_exposure_percent": "80.0",
                "min_confidence": "0.65",
                "crowded_long_zscore": "2.0",
                "crowded_short_zscore": "-2.0",
            },
        ),
        SymbolTier.TIER_3: SymbolTierConfigSchema.model_validate(
            {
                "risk_per_trade_percent": "2.0",
                "max_leverage": 2,
                "max_exposure_percent": "10.0",
                "min_confidence": "0.85",
                "crowded_long_zscore": "3.0",
                "crowded_short_zscore": "-3.0",
            },
        ),
    }
    symbol_map = {
        "BTCUSDT": SymbolTier.TIER_1,
        "ETHUSDT": SymbolTier.TIER_1,
    }
    return SymbolTierRegistry(tier_configs=tier_configs, symbol_map=symbol_map)


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

    @pytest.mark.asyncio
    async def test_rejects_when_portfolio_risk_exceeds_cap(
        self, mock_state_manager
    ) -> None:
        """One open TIER_1 (4%) + new TIER_1 (4%) = 8% > 2.5% cap → rejected."""
        validator = DynamicRiskValidator(tier_registry=make_tier_registry())
        mock_state_manager.get_all_positions = AsyncMock(
            return_value=[make_position("BTCUSDT")],
        )

        result = await validator.validate_trade(
            symbol="ETHUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("portfolio risk" in r.lower() for r in result.rejection_reasons)

    # =========================================================================
    # C5 — EXTREME regime confidence bypass (report_2026_06_11b)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_extreme_regime_blocked_without_confidence_override(
        self, mock_state_manager
    ) -> None:
        """Default config does not allow confidence to override EXTREME block."""
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
            confidence=Decimal("0.95"),
        )

        assert result.is_valid is False
        assert result.volatility_regime == VolatilityRegime.EXTREME
        assert any("extreme" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_extreme_regime_passes_with_high_confidence_when_opt_in_enabled(
        self, mock_state_manager
    ) -> None:
        """EXTREME regime passes when opt-in enabled and confidence >= threshold."""
        from kavzi_trader.spine.risk.config import RiskConfigSchema

        config = RiskConfigSchema(
            extreme_high_confidence_pass=True,
            extreme_min_confidence_override=Decimal("0.80"),
        )
        validator = DynamicRiskValidator(config=config)
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
            confidence=Decimal("0.85"),
        )

        assert result.volatility_regime == VolatilityRegime.EXTREME
        assert not any("extreme" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_extreme_regime_blocked_when_confidence_below_override_threshold(
        self, mock_state_manager
    ) -> None:
        """Even with opt-in enabled, confidence < threshold keeps the block in place."""
        from kavzi_trader.spine.risk.config import RiskConfigSchema

        config = RiskConfigSchema(
            extreme_high_confidence_pass=True,
            extreme_min_confidence_override=Decimal("0.80"),
        )
        validator = DynamicRiskValidator(config=config)
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
            confidence=Decimal("0.70"),
        )

        assert result.is_valid is False
        assert result.volatility_regime == VolatilityRegime.EXTREME
        assert any("extreme" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_allows_single_position_below_cap(self, mock_state_manager) -> None:
        """Zero open positions + single TIER_1 (4%) < 4.5% cap → no rejection."""
        from kavzi_trader.spine.risk.config import RiskConfigSchema

        # pause=5% → cap = 5 - 0.5 = 4.5%, so a lone 4% trade fits.
        # close-all must stay above pause to satisfy the config ordering check.
        config = RiskConfigSchema(
            drawdown_pause_percent=Decimal("5.0"),
            drawdown_close_all_percent=Decimal("8.0"),
        )
        validator = DynamicRiskValidator(
            config=config,
            tier_registry=make_tier_registry(),
        )
        mock_state_manager.get_all_positions = AsyncMock(return_value=[])

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

        assert not any("portfolio risk" in r.lower() for r in result.rejection_reasons)

    # =========================================================================
    # Regime policy, SL side check and filter multiplier (M3)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_tier1_extreme_gets_quarter_size(self, mock_state_manager) -> None:
        """TIER_1 passes EXTREME and is sized at 0.25x, not zero."""
        config = RiskConfigSchema(risk_per_trade_percent=Decimal("0.1"))
        validator = DynamicRiskValidator(config=config)

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(120),
            atr_history=_EXTREME_ATR_HISTORY,
            state_manager=mock_state_manager,
            symbol_tier="TIER_1",
        )

        assert result.is_valid is True
        assert result.volatility_regime == VolatilityRegime.EXTREME
        # risk 10 / stop 100 = 0.1 BTC, x0.25
        assert result.recommended_size == Decimal("0.025")

    @pytest.mark.asyncio
    async def test_confidence_override_in_extreme_gets_quarter_size(
        self, mock_state_manager
    ) -> None:
        config = RiskConfigSchema(
            risk_per_trade_percent=Decimal("0.1"),
            extreme_high_confidence_pass=True,
        )
        validator = DynamicRiskValidator(config=config)

        result = await validator.validate_trade(
            symbol="SOLUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(120),
            atr_history=_EXTREME_ATR_HISTORY,
            state_manager=mock_state_manager,
            confidence=Decimal("0.85"),
            symbol_tier="TIER_2",
        )

        assert result.is_valid is True
        assert result.recommended_size == Decimal("0.025")

    @pytest.mark.asyncio
    async def test_wrong_side_stop_rejected_when_atr_is_zero(
        self, mock_state_manager
    ) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(50100),
            take_profit=Decimal(50200),
            current_atr=Decimal(0),
            atr_history=[Decimal(5)] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any(
            "must be below entry for LONG" in r for r in result.rejection_reasons
        )
        assert any("ATR unavailable" in r for r in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_filter_size_multiplier_scales_recommended_size(
        self, mock_state_manager
    ) -> None:
        config = RiskConfigSchema(risk_per_trade_percent=Decimal("0.1"))
        validator = DynamicRiskValidator(config=config)

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 9 + [Decimal(101)],
            state_manager=mock_state_manager,
            size_multiplier=Decimal("0.5"),
        )

        # risk 10 / stop 100 = 0.1 BTC, halved by the filters
        assert result.is_valid is True
        assert result.recommended_size == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_filter_reduction_below_min_notional_is_rejected(
        self, mock_state_manager
    ) -> None:
        config = RiskConfigSchema(risk_per_trade_percent=Decimal("0.1"))
        validator = DynamicRiskValidator(config=config)

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49900),
            take_profit=Decimal(50200),
            current_atr=Decimal(100),
            atr_history=[Decimal(100)] * 9 + [Decimal(101)],
            state_manager=mock_state_manager,
            size_multiplier=Decimal("0.001"),
        )

        # 0.1 BTC x 0.001 = 0.0001 BTC = $5 < $10 floor
        assert result.is_valid is False
        assert any("below minimum" in r for r in result.rejection_reasons)


class TestLiquidationUsesPositionNotional:
    @pytest.mark.asyncio
    async def test_small_btc_trade_uses_sized_notional_not_unit_price(
        self, mock_state_manager
    ) -> None:
        """Regression: notional was the ~90k per-unit price, picking bracket 2."""
        calc = MagicMock(spec=LiquidationCalculator)
        calc.estimate_liquidation_price = AsyncMock(return_value=Decimal(1))
        validator = DynamicRiskValidator(liquidation_calculator=calc)

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(90000),
            stop_loss=Decimal(84000),
            take_profit=Decimal(102000),
            current_atr=Decimal(3000),
            atr_history=[Decimal(3000)] * 10,
            state_manager=mock_state_manager,
            leverage=10,
        )

        assert result.is_valid is True
        notional = calc.estimate_liquidation_price.await_args.kwargs["notional"]
        assert notional == result.recommended_size * Decimal(90000)
        assert notional < Decimal(50000), "Expected a bracket 1 sized position"

    @pytest.mark.asyncio
    async def test_small_btc_trade_is_judged_with_bracket_1_mmr(
        self, mock_state_manager, bracketed_liquidation_calculator
    ) -> None:
        """Bracket 1 liq is 81360; the unit-price bracket would give 85500."""
        validator = DynamicRiskValidator(
            liquidation_calculator=bracketed_liquidation_calculator,
        )

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(90000),
            stop_loss=Decimal(84000),
            take_profit=Decimal(102000),
            current_atr=Decimal(3000),
            atr_history=[Decimal(3000)] * 10,
            state_manager=mock_state_manager,
            leverage=10,
        )

        assert result.rejection_reasons == []
        assert result.is_valid is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("side", "stop_loss", "take_profit", "atr", "is_valid"),
        [
            # LONG: liq 81360, buffered safe threshold 83088
            ("LONG", Decimal(81000), Decimal(110000), Decimal(4500), False),
            ("LONG", Decimal(83000), Decimal(105000), Decimal(3500), False),
            ("LONG", Decimal(84000), Decimal(102000), Decimal(3000), True),
            # SHORT: liq 98640, buffered safe threshold 96912
            ("SHORT", Decimal(99000), Decimal(72000), Decimal(4500), False),
            ("SHORT", Decimal(97000), Decimal(75000), Decimal(3500), False),
            ("SHORT", Decimal(96000), Decimal(78000), Decimal(3000), True),
        ],
    )
    async def test_stop_loss_vs_liquidation_by_side(
        self,
        mock_state_manager,
        bracketed_liquidation_calculator,
        side,
        stop_loss,
        take_profit,
        atr,
        is_valid,
    ) -> None:
        validator = DynamicRiskValidator(
            liquidation_calculator=bracketed_liquidation_calculator,
        )

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side=side,
            entry_price=Decimal(90000),
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_atr=atr,
            atr_history=[atr] * 10,
            state_manager=mock_state_manager,
            leverage=10,
        )

        assert result.is_valid is is_valid, result.rejection_reasons
        if not is_valid:
            assert any("liquidation" in r.lower() for r in result.rejection_reasons)
            assert result.recommended_size == Decimal(0)

    @pytest.mark.asyncio
    async def test_liquidation_reason_kept_alongside_other_rejections(
        self, mock_state_manager, bracketed_liquidation_calculator
    ) -> None:
        validator = DynamicRiskValidator(
            liquidation_calculator=bracketed_liquidation_calculator,
        )

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(90000),
            stop_loss=Decimal(81000),
            take_profit=Decimal(91000),
            current_atr=Decimal(4500),
            atr_history=[Decimal(4500)] * 10,
            state_manager=mock_state_manager,
            leverage=10,
        )

        reasons = [r.lower() for r in result.rejection_reasons]
        assert any("r:r" in r for r in reasons), reasons
        assert any("liquidation" in r for r in reasons), reasons
        assert result.recommended_size == Decimal(0)

    @pytest.mark.asyncio
    async def test_liquidation_notional_includes_filter_size_multiplier(
        self, mock_state_manager
    ) -> None:
        calc = MagicMock(spec=LiquidationCalculator)
        calc.estimate_liquidation_price = AsyncMock(return_value=Decimal(1))
        validator = DynamicRiskValidator(liquidation_calculator=calc)
        trade = {
            "symbol": "BTCUSDT",
            "side": "LONG",
            "entry_price": Decimal(90000),
            "stop_loss": Decimal(84000),
            "take_profit": Decimal(102000),
            "current_atr": Decimal(3000),
            "atr_history": [Decimal(3000)] * 10,
            "state_manager": mock_state_manager,
            "leverage": 10,
        }

        full = await validator.validate_trade(**trade)
        reduced = await validator.validate_trade(
            **trade,
            size_multiplier=Decimal("0.5"),
        )

        notional = calc.estimate_liquidation_price.await_args.kwargs["notional"]
        assert reduced.recommended_size < full.recommended_size
        assert notional == reduced.recommended_size * Decimal(90000)
