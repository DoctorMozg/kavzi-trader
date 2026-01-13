from datetime import UTC, datetime
from decimal import Decimal

from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.state.schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)


def make_position(symbol: str, position_id: str = "pos-1") -> PositionSchema:
    return PositionSchema(
        id=position_id,
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


class TestExposureLimiter:
    def test_allows_first_position(self, risk_config: RiskConfigSchema) -> None:
        limiter = ExposureLimiter(risk_config)
        result = limiter.check_exposure("BTCUSDT", [])

        assert result.is_allowed is True
        assert result.current_position_count == 0
        assert result.rejection_reason is None

    def test_allows_second_position_different_symbol(
        self,
        risk_config: RiskConfigSchema,
    ) -> None:
        limiter = ExposureLimiter(risk_config)
        positions = [make_position("BTCUSDT")]

        result = limiter.check_exposure("ETHUSDT", positions)

        assert result.is_allowed is True
        assert result.current_position_count == 1

    def test_rejects_at_max_positions(self, risk_config: RiskConfigSchema) -> None:
        limiter = ExposureLimiter(risk_config)
        positions = [
            make_position("BTCUSDT", "pos-1"),
            make_position("ETHUSDT", "pos-2"),
        ]

        result = limiter.check_exposure("SOLUSDT", positions)

        assert result.is_allowed is False
        assert result.current_position_count == 2
        assert "Max positions reached" in str(result.rejection_reason)

    def test_rejects_duplicate_symbol(self, risk_config: RiskConfigSchema) -> None:
        limiter = ExposureLimiter(risk_config)
        positions = [make_position("BTCUSDT")]

        result = limiter.check_exposure("BTCUSDT", positions)

        assert result.is_allowed is False
        assert "Already have position in BTCUSDT" in str(result.rejection_reason)

    def test_custom_max_positions(self) -> None:
        config = RiskConfigSchema(max_positions=3)
        limiter = ExposureLimiter(config)
        positions = [
            make_position("BTCUSDT", "pos-1"),
            make_position("ETHUSDT", "pos-2"),
        ]

        result = limiter.check_exposure("SOLUSDT", positions)

        assert result.is_allowed is True
        assert result.max_positions == 3

    def test_single_position_limit(self) -> None:
        config = RiskConfigSchema(max_positions=1)
        limiter = ExposureLimiter(config)
        positions = [make_position("BTCUSDT")]

        result = limiter.check_exposure("ETHUSDT", positions)

        assert result.is_allowed is False
        assert result.max_positions == 1
