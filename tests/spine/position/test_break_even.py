from datetime import UTC, datetime, timedelta
from decimal import Decimal

from kavzi_trader.spine.position.break_even import BreakEvenMover
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


def test_break_even_moves_stop_loss_for_long(position_factory) -> None:
    opened_at = datetime.now(UTC) - timedelta(seconds=1200)
    position = position_factory(
        current_stop_loss=Decimal(90),
        opened_at=opened_at,
    )
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(115),
        current_atr=Decimal(10),
    )

    assert action is not None
    assert action.action == PositionActionType.MOVE_STOP_LOSS
    assert action.new_stop_loss == position.entry_price
    assert action.reason == "break_even"


def test_break_even_skips_if_already_moved(position_factory) -> None:
    position = position_factory(stop_loss_moved_to_breakeven=True)
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(115),
        current_atr=Decimal(10),
    )

    assert action is None


def test_break_even_requires_profit_threshold(position_factory) -> None:
    position = position_factory()
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(105),
        current_atr=Decimal(10),
    )

    assert action is None


def test_break_even_moves_stop_loss_for_short(position_factory) -> None:
    opened_at = datetime.now(UTC) - timedelta(seconds=1200)
    position = position_factory(
        side="SHORT",
        stop_loss=Decimal(110),
        current_stop_loss=Decimal(110),
        take_profit=Decimal(80),
        opened_at=opened_at,
    )
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(85),
        current_atr=Decimal(10),
    )

    assert action is not None
    assert action.action == PositionActionType.MOVE_STOP_LOSS
    assert action.new_stop_loss == position.entry_price


def test_break_even_skips_when_position_too_young(position_factory) -> None:
    opened_at = datetime.now(UTC) - timedelta(seconds=300)
    position = position_factory(
        current_stop_loss=Decimal(90),
        opened_at=opened_at,
    )
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(120),
        current_atr=Decimal(10),
    )

    assert action is None


def test_break_even_activates_when_position_old_enough(position_factory) -> None:
    opened_at = datetime.now(UTC) - timedelta(seconds=1200)
    position = position_factory(
        current_stop_loss=Decimal(90),
        opened_at=opened_at,
    )
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(120),
        current_atr=Decimal(10),
    )

    assert action is not None
    assert action.action == PositionActionType.MOVE_STOP_LOSS
    assert action.new_stop_loss == position.entry_price


def test_break_even_skips_time_guard_when_disabled(position_factory) -> None:
    opened_at = datetime.now(UTC) - timedelta(seconds=10)
    config = PositionManagementConfigSchema(break_even_min_hold_s=0)
    position = position_factory(
        current_stop_loss=Decimal(90),
        opened_at=opened_at,
        management_config=config,
    )
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(120),
        current_atr=Decimal(10),
    )

    assert action is not None
    assert action.action == PositionActionType.MOVE_STOP_LOSS
