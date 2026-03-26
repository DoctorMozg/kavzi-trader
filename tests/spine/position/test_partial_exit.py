from decimal import Decimal

from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.position_action_type import PositionActionType


def test_partial_exit_triggers_at_halfway_to_tp(position_factory) -> None:
    position = position_factory(entry_price=Decimal(100), take_profit=Decimal(120))
    checker = PartialExitChecker()

    action = checker.evaluate(position=position, current_price=Decimal(110))

    assert action is not None
    assert action.action == PositionActionType.PARTIAL_EXIT
    assert action.exit_quantity == Decimal("0.3")


def test_partial_exit_skips_if_done(position_factory) -> None:
    position = position_factory(partial_exit_done=True)
    checker = PartialExitChecker()

    action = checker.evaluate(position=position, current_price=Decimal(110))

    assert action is None


def test_partial_exit_requires_progress(position_factory) -> None:
    position = position_factory(entry_price=Decimal(100), take_profit=Decimal(120))
    checker = PartialExitChecker()

    action = checker.evaluate(position=position, current_price=Decimal(105))

    assert action is None
