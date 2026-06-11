from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)


def _make_position(
    *,
    symbol: str = "BTCUSDT",
    entry_price: Decimal = Decimal(100),
    stop_loss: Decimal = Decimal(95),
    current_stop_loss: Decimal = Decimal(95),
    stop_loss_moved_to_breakeven: bool = False,
) -> PositionSchema:
    now = utc_now()
    return PositionSchema(
        id="pos-1",
        symbol=symbol,
        side="LONG",
        quantity=Decimal("0.5"),
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=Decimal(120),
        current_stop_loss=current_stop_loss,
        management_config=PositionManagementConfigSchema(),
        stop_loss_moved_to_breakeven=stop_loss_moved_to_breakeven,
        partial_exit_done=False,
        opened_at=now,
        updated_at=now,
    )


def _make_loop(
    *,
    manager: AsyncMock | None = None,
    state_manager: AsyncMock | None = None,
    atr_provider: AsyncMock | None = None,
    price_provider: AsyncMock | None = None,
    action_executor: AsyncMock | None = None,
) -> PositionManagementLoop:
    return PositionManagementLoop(
        manager=manager or AsyncMock(),
        state_manager=state_manager or AsyncMock(),
        atr_provider=atr_provider or AsyncMock(),
        price_provider=price_provider or AsyncMock(),
        action_executor=action_executor or AsyncMock(),
        interval_s=5,
    )


# ---- F14: Zero price guard --------------------------------------------------


@pytest.mark.asyncio
async def test_zero_price_skips_position_management() -> None:
    """When price provider returns 0, evaluate_position must NOT be called."""
    manager = AsyncMock()
    price_provider = AsyncMock()
    price_provider.get_current_price = AsyncMock(return_value=Decimal(0))
    atr_provider = AsyncMock()
    atr_provider.get_atr = AsyncMock(return_value=Decimal(5))

    loop = _make_loop(
        manager=manager,
        price_provider=price_provider,
        atr_provider=atr_provider,
    )
    position = _make_position()
    await loop._manage_single_position(position)

    manager.evaluate_position.assert_not_called()


# ---- F10: Position refresh after multi-action --------------------------------


@pytest.mark.asyncio
async def test_position_refreshed_between_actions() -> None:
    """After applying the first action, the loop must re-fetch the position
    from state before applying the second action."""
    position = _make_position()
    refreshed = _make_position(current_stop_loss=Decimal(102))

    partial_exit_action = PositionActionSchema(
        action=PositionActionType.PARTIAL_EXIT,
        exit_quantity=Decimal("0.1"),
        reason="partial_profit",
    )
    exit_action = PositionActionSchema(
        action=PositionActionType.FULL_EXIT,
        reason="time_exit",
    )

    manager = AsyncMock()
    manager.evaluate_position = AsyncMock(
        return_value=[partial_exit_action, exit_action],
    )

    state_manager = AsyncMock()
    state_manager.get_position = AsyncMock(return_value=refreshed)
    state_manager.update_position = AsyncMock()

    action_executor = AsyncMock()
    action_executor.execute = AsyncMock(return_value=None)

    price_provider = AsyncMock()
    price_provider.get_current_price = AsyncMock(return_value=Decimal(105))
    atr_provider = AsyncMock()
    atr_provider.get_atr = AsyncMock(return_value=Decimal(5))

    loop = _make_loop(
        manager=manager,
        state_manager=state_manager,
        action_executor=action_executor,
        price_provider=price_provider,
        atr_provider=atr_provider,
    )

    await loop._manage_single_position(position)

    # After the first (non-FULL_EXIT) action, state must be refreshed
    state_manager.get_position.assert_called_with(position.symbol)
