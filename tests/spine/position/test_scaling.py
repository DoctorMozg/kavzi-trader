from decimal import Decimal

from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.position.scaling import ScaleInChecker
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


def test_scale_in_triggers_on_small_retrace(position_factory) -> None:
    config = PositionManagementConfigSchema(scale_in_allowed=True)
    position = position_factory(management_config=config)
    checker = ScaleInChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal("104"),
        current_atr=Decimal("10"),
    )

    assert action is not None
    assert action.action == PositionActionType.SCALE_IN
    assert action.scale_in_quantity == Decimal("0.5")


def test_scale_in_skips_when_profit_too_large(position_factory) -> None:
    config = PositionManagementConfigSchema(scale_in_allowed=True)
    position = position_factory(management_config=config)
    checker = ScaleInChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal("108"),
        current_atr=Decimal("10"),
    )

    assert action is None


def test_scale_in_skips_when_disabled(position_factory) -> None:
    position = position_factory()
    checker = ScaleInChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal("104"),
        current_atr=Decimal("10"),
    )

    assert action is None
