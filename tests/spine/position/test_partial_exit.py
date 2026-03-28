from decimal import Decimal

from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


def test_partial_exit_triggers_at_threshold(position_factory) -> None:
    config = PositionManagementConfigSchema(partial_exit_min_profit_atr=Decimal(0))
    position = position_factory(
        entry_price=Decimal(100),
        take_profit=Decimal(120),
        management_config=config,
    )
    checker = PartialExitChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(113),
        current_atr=Decimal(10),
    )

    assert action is not None
    assert action.action == PositionActionType.PARTIAL_EXIT
    assert action.exit_quantity == Decimal("0.3")


def test_partial_exit_skips_if_done(position_factory) -> None:
    position = position_factory(partial_exit_done=True)
    checker = PartialExitChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(113),
        current_atr=Decimal(10),
    )

    assert action is None


def test_partial_exit_requires_progress(position_factory) -> None:
    position = position_factory(entry_price=Decimal(100), take_profit=Decimal(120))
    checker = PartialExitChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(105),
        current_atr=Decimal(10),
    )

    assert action is None


def test_partial_exit_skips_when_atr_profit_too_low(position_factory) -> None:
    config = PositionManagementConfigSchema(
        partial_exit_at_percent=Decimal("0.5"),
    )
    position = position_factory(
        entry_price=Decimal(100),
        take_profit=Decimal(120),
        management_config=config,
    )
    checker = PartialExitChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(110),
        current_atr=Decimal(15),
    )

    assert action is None
