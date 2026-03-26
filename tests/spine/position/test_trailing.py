from decimal import Decimal

from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.position.trailing import TrailingStopChecker


def test_trailing_moves_stop_loss_after_two_atr(position_factory) -> None:
    position = position_factory(current_stop_loss=Decimal(90))
    checker = TrailingStopChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(130),
        current_atr=Decimal(10),
    )

    assert action is not None
    assert action.action == PositionActionType.MOVE_STOP_LOSS
    assert action.new_stop_loss == Decimal(115)


def test_trailing_skips_when_profit_is_small(position_factory) -> None:
    position = position_factory(current_stop_loss=Decimal(90))
    checker = TrailingStopChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(115),
        current_atr=Decimal(10),
    )

    assert action is None


def test_trailing_skips_if_stop_loss_not_improved(position_factory) -> None:
    position = position_factory(current_stop_loss=Decimal(120))
    checker = TrailingStopChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(130),
        current_atr=Decimal(10),
    )

    assert action is None
