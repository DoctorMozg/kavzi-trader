from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.api.common.models import OrderStatus
from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.risk.schemas import RiskValidationResultSchema, VolatilityRegime


@pytest.mark.asyncio()
async def test_engine_rejects_stale(
    decision_message,
    execution_config: ExecutionConfigSchema,
) -> None:
    exchange = AsyncMock()
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    staleness_checker = StalenessChecker(execution_config)
    translator = DecisionTranslator()
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
    )

    result = await engine.execute(decision_message)

    assert result.status == "EXPIRED"
    exchange.create_order.assert_not_called()


@pytest.mark.asyncio()
async def test_engine_rejects_risk(
    decision_message,
    execution_config: ExecutionConfigSchema,
) -> None:
    exchange = AsyncMock()
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    risk_validator.validate_trade = AsyncMock(
        return_value=RiskValidationResultSchema(
            is_valid=False,
            rejection_reasons=["bad risk"],
            volatility_regime=VolatilityRegime.NORMAL,
            recommended_size=Decimal("0"),
            size_multiplier=Decimal("1"),
            warnings=[],
            should_close_all=False,
        ),
    )
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    translator = DecisionTranslator()
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
    )

    result = await engine.execute(decision_message)

    assert result.status == "REJECTED"
    exchange.create_order.assert_not_called()


@pytest.mark.asyncio()
async def test_engine_executes_filled_order(
    decision_message,
    execution_config: ExecutionConfigSchema,
    filled_order_response,
) -> None:
    exchange = AsyncMock()
    exchange.create_order = AsyncMock(return_value=filled_order_response)
    state_manager = AsyncMock()
    risk_validator = AsyncMock()
    risk_validator.validate_trade = AsyncMock(
        return_value=RiskValidationResultSchema(
            is_valid=True,
            rejection_reasons=[],
            volatility_regime=VolatilityRegime.NORMAL,
            recommended_size=Decimal("1"),
            size_multiplier=Decimal("1"),
            warnings=[],
            should_close_all=False,
        ),
    )
    staleness_checker = MagicMock()
    staleness_checker.is_stale.return_value = False
    translator = DecisionTranslator()
    monitor = OrderMonitor(exchange=exchange, timeout_s=1)

    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=risk_validator,
        staleness_checker=staleness_checker,
        translator=translator,
        monitor=monitor,
        event_store=None,
    )

    result = await engine.execute(decision_message)

    assert result.status == "FILLED"
    assert result.order_id == str(filled_order_response.order_id)
    assert result.executed_qty == float(filled_order_response.executed_qty)
    assert filled_order_response.status == OrderStatus.FILLED
    state_manager.save_order.assert_called_once()
    state_manager.update_position.assert_called_once()
