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
        partial_exit_at_fraction=Decimal("0.5"),
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


def test_partial_exit_uses_atr_at_entry_not_current_atr(position_factory) -> None:
    """Volatility expansion after entry must not suppress a valid partial exit.

    With entry ATR=5 and current ATR=50 (10x expansion), profit_atr against
    current_atr would be 0.5 < 1.0 threshold → would wrongly block. Using
    atr_at_entry=5 gives profit_atr=5.0 → correctly triggers.
    """
    config = PositionManagementConfigSchema(
        partial_exit_at_fraction=Decimal("0.5"),
        partial_exit_min_profit_atr=Decimal("1.0"),
    )
    position = position_factory(
        entry_price=Decimal(100),
        take_profit=Decimal(130),
        atr_at_entry=Decimal(5),
        management_config=config,
    )
    checker = PartialExitChecker()

    # current_price=125 → progress=83%, profit=25; current_atr=50 inflated by
    # volatility expansion; atr_at_entry=5 gives profit_atr=5.0 → triggers
    action = checker.evaluate(
        position=position,
        current_price=Decimal(125),
        current_atr=Decimal(50),
    )

    assert action is not None
    assert action.action == PositionActionType.PARTIAL_EXIT


def test_partial_exit_falls_back_to_current_atr_when_no_entry_atr(
    position_factory,
) -> None:
    """When atr_at_entry is None, current_atr is the reference (backward compat)."""
    config = PositionManagementConfigSchema(
        partial_exit_at_fraction=Decimal("0.5"),
        partial_exit_min_profit_atr=Decimal("1.0"),
    )
    position = position_factory(
        entry_price=Decimal(100),
        take_profit=Decimal(120),
        atr_at_entry=None,
        management_config=config,
    )
    checker = PartialExitChecker()

    # profit=10, current_atr=15 → profit_atr=0.67 < 1.0 → should skip
    action = checker.evaluate(
        position=position,
        current_price=Decimal(110),
        current_atr=Decimal(15),
    )

    assert action is None
