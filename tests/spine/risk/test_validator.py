from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

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
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("52000"),
        current_stop_loss=Decimal("49000"),
        management_config=PositionManagementConfigSchema(),
        opened_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestDynamicRiskValidator:
    @pytest.mark.asyncio()
    async def test_valid_trade_passes(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        atr_history = [Decimal("100")] * 10

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("100"),
            atr_history=atr_history,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is True
        assert result.rejection_reasons == []
        assert result.volatility_regime == VolatilityRegime.NORMAL

    @pytest.mark.asyncio()
    async def test_rejects_high_drawdown(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        mock_state_manager.get_current_drawdown = AsyncMock(return_value=Decimal("4.0"))

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("drawdown" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio()
    async def test_close_all_triggered_at_5_percent(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        mock_state_manager.get_current_drawdown = AsyncMock(return_value=Decimal("6.0"))

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert result.should_close_all is True

    @pytest.mark.asyncio()
    async def test_rejects_max_positions(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        mock_state_manager.get_all_positions = AsyncMock(
            return_value=[make_position("BTCUSDT"), make_position("ETHUSDT")],
        )

        result = await validator.validate_trade(
            symbol="SOLUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("max positions" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio()
    async def test_rejects_extreme_volatility(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        atr_history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("120"),
            atr_history=atr_history,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert result.volatility_regime == VolatilityRegime.EXTREME

    @pytest.mark.asyncio()
    async def test_rejects_low_volatility(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        atr_history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("92"),
            atr_history=atr_history,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert result.volatility_regime == VolatilityRegime.LOW

    @pytest.mark.asyncio()
    async def test_rejects_stop_loss_too_tight(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49990"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("too tight" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio()
    async def test_rejects_stop_loss_too_wide(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49500"),
            take_profit=Decimal("52000"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("too wide" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio()
    async def test_rejects_poor_risk_reward(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50050"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("r:r ratio" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio()
    async def test_rejects_long_with_sl_above_entry(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("50100"),
            take_profit=Decimal("51000"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("below entry" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio()
    async def test_rejects_short_with_sl_below_entry(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="SHORT",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("49000"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is False
        assert any("above entry" in r.lower() for r in result.rejection_reasons)

    @pytest.mark.asyncio()
    async def test_high_volatility_warning(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        atr_history = [
            Decimal(str(i)) for i in [95, 100, 105, 98, 102, 97, 103, 99, 101, 100]
        ]

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("105"),
            atr_history=atr_history,
            state_manager=mock_state_manager,
        )

        assert result.volatility_regime == VolatilityRegime.HIGH
        assert any("high volatility" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio()
    async def test_calculates_recommended_size(self, mock_state_manager) -> None:
        validator = DynamicRiskValidator()
        mock_state_manager.get_account_state = AsyncMock(
            return_value=AccountStateSchema(
                total_balance_usdt=Decimal("10000"),
                available_balance_usdt=Decimal("10000"),
                locked_balance_usdt=Decimal("0"),
                peak_balance=Decimal("10000"),
                updated_at=datetime.now(UTC),
            ),
        )

        result = await validator.validate_trade(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49900"),
            take_profit=Decimal("50200"),
            current_atr=Decimal("100"),
            atr_history=[Decimal("100")] * 10,
            state_manager=mock_state_manager,
        )

        assert result.is_valid is True
        assert result.recommended_size > Decimal("0")
