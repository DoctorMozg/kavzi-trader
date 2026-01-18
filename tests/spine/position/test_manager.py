from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kavzi_trader.spine.position.break_even import BreakEvenMover
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.scaling import ScaleInChecker
from kavzi_trader.spine.position.time_exit import TimeExitChecker
from kavzi_trader.spine.position.trailing import TrailingStopChecker


def build_manager() -> PositionManager:
    return PositionManager(
        break_even=BreakEvenMover(),
        trailing=TrailingStopChecker(),
        partial_exit=PartialExitChecker(),
        time_exit=TimeExitChecker(),
        scaling=ScaleInChecker(),
    )


@pytest.mark.asyncio()
async def test_manager_returns_time_exit_only(position_factory, monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    opened_at = now - timedelta(hours=30)
    position = position_factory(opened_at=opened_at, updated_at=opened_at)
    manager = build_manager()

    monkeypatch.setattr(
        "kavzi_trader.spine.position.time_exit.utc_now",
        lambda: now,
    )

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal("110"),
        current_atr=Decimal("10"),
    )

    assert actions is not None
    assert len(actions) == 1
    assert actions[0].reason == "time_exit"


@pytest.mark.asyncio()
async def test_manager_prefers_trailing_over_break_even(position_factory) -> None:
    position = position_factory(current_stop_loss=Decimal("90"))
    manager = build_manager()

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal("130"),
        current_atr=Decimal("10"),
    )

    assert any(action.reason == "trailing_stop" for action in actions)


@pytest.mark.asyncio()
async def test_manager_returns_break_even_when_trailing_not_ready(
    position_factory,
) -> None:
    position = position_factory(current_stop_loss=Decimal("90"))
    manager = build_manager()

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal("112"),
        current_atr=Decimal("10"),
    )

    assert any(action.reason == "break_even" for action in actions)


@pytest.mark.asyncio()
async def test_manager_includes_partial_exit(position_factory) -> None:
    position = position_factory(entry_price=Decimal("100"), take_profit=Decimal("120"))
    manager = build_manager()

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal("110"),
        current_atr=Decimal("10"),
    )

    assert any(action.reason == "partial_exit" for action in actions)
