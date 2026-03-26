from decimal import Decimal

from kavzi_trader.spine.position.break_even import BreakEvenMover
from kavzi_trader.spine.position.position_action_type import PositionActionType


def test_break_even_moves_stop_loss_for_long(position_factory) -> None:
    position = position_factory(current_stop_loss=Decimal(90))
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(110),
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
        current_price=Decimal(110),
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
    position = position_factory(
        side="SHORT",
        stop_loss=Decimal(110),
        current_stop_loss=Decimal(110),
        take_profit=Decimal(80),
    )
    mover = BreakEvenMover()

    action = mover.evaluate(
        position=position,
        current_price=Decimal(90),
        current_atr=Decimal(10),
    )

    assert action is not None
    assert action.action == PositionActionType.MOVE_STOP_LOSS
    assert action.new_stop_loss == position.entry_price
