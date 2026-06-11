from datetime import UTC, datetime, timedelta
from decimal import Decimal

from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.position.stall_exit import StallExitChecker
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


def test_no_exit_before_stall_window(position_factory) -> None:
    config = PositionManagementConfigSchema(stall_check_after_hours=8)
    opened_at = datetime.now(UTC) - timedelta(hours=7)
    position = position_factory(
        opened_at=opened_at, updated_at=opened_at, management_config=config
    )
    checker = StallExitChecker()

    assert checker.evaluate(position, Decimal(100), Decimal(5)) is None


def test_exits_when_no_progress_after_window(position_factory) -> None:
    config = PositionManagementConfigSchema(
        stall_check_after_hours=8,
        stall_min_progress_atr=Decimal("0.3"),
    )
    opened_at = datetime.now(UTC) - timedelta(hours=10)
    position = position_factory(
        entry_price=Decimal(100),
        opened_at=opened_at,
        updated_at=opened_at,
        atr_at_entry=Decimal(5),
        management_config=config,
    )
    checker = StallExitChecker()

    # price at entry = no profit
    action = checker.evaluate(position, Decimal(100), Decimal(5))

    assert action is not None
    assert action.action == PositionActionType.FULL_EXIT
    assert action.reason == "stall_exit"


def test_exits_when_progress_below_threshold(position_factory) -> None:
    config = PositionManagementConfigSchema(
        stall_check_after_hours=8,
        stall_min_progress_atr=Decimal("0.5"),
    )
    opened_at = datetime.now(UTC) - timedelta(hours=10)
    position = position_factory(
        entry_price=Decimal(100),
        opened_at=opened_at,
        updated_at=opened_at,
        atr_at_entry=Decimal(10),
        management_config=config,
    )
    checker = StallExitChecker()

    # profit=2, atr_at_entry=10 → progress_atr=0.2 < 0.5 threshold → stall
    action = checker.evaluate(position, Decimal(102), Decimal(10))

    assert action is not None
    assert action.action == PositionActionType.FULL_EXIT


def test_no_exit_when_progress_above_threshold(position_factory) -> None:
    config = PositionManagementConfigSchema(
        stall_check_after_hours=8,
        stall_min_progress_atr=Decimal("0.3"),
    )
    opened_at = datetime.now(UTC) - timedelta(hours=10)
    position = position_factory(
        entry_price=Decimal(100),
        opened_at=opened_at,
        updated_at=opened_at,
        atr_at_entry=Decimal(5),
        management_config=config,
    )
    checker = StallExitChecker()

    # profit=5, atr_at_entry=5 → progress_atr=1.0 > 0.3 → no stall
    action = checker.evaluate(position, Decimal(105), Decimal(5))

    assert action is None


def test_stall_exit_works_for_short(position_factory) -> None:
    config = PositionManagementConfigSchema(
        stall_check_after_hours=8,
        stall_min_progress_atr=Decimal("0.5"),
    )
    opened_at = datetime.now(UTC) - timedelta(hours=12)
    position = position_factory(
        side="SHORT",
        entry_price=Decimal(100),
        stop_loss=Decimal(110),
        take_profit=Decimal(80),
        opened_at=opened_at,
        updated_at=opened_at,
        atr_at_entry=Decimal(10),
        management_config=config,
    )
    checker = StallExitChecker()

    # SHORT: progress = entry - current = 100 - 99 = 1; atr=10 → 0.1 < 0.5
    action = checker.evaluate(position, Decimal(99), Decimal(10))

    assert action is not None
    assert action.action == PositionActionType.FULL_EXIT


def test_stall_exit_falls_back_to_current_atr_when_no_entry_atr(
    position_factory,
) -> None:
    config = PositionManagementConfigSchema(
        stall_check_after_hours=8,
        stall_min_progress_atr=Decimal("0.3"),
    )
    opened_at = datetime.now(UTC) - timedelta(hours=10)
    position = position_factory(
        entry_price=Decimal(100),
        opened_at=opened_at,
        updated_at=opened_at,
        atr_at_entry=None,
        management_config=config,
    )
    checker = StallExitChecker()

    # No atr_at_entry → falls back to current_atr=5; profit=5 → progress_atr=1.0
    action = checker.evaluate(position, Decimal(105), Decimal(5))

    assert action is None
