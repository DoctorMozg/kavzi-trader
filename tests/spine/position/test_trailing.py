from decimal import Decimal

from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.position.trailing import TrailingStopChecker
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema


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


def test_trailing_respects_configurable_trigger(position_factory) -> None:
    config = PositionManagementConfigSchema(trailing_stop_trigger_atr=Decimal("1.0"))
    position = position_factory(
        current_stop_loss=Decimal(90),
        management_config=config,
    )
    checker = TrailingStopChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(115),
        current_atr=Decimal(10),
    )

    assert action is not None
    assert action.action == PositionActionType.MOVE_STOP_LOSS
    assert action.new_stop_loss == Decimal(100)


def test_trailing_blocked_below_half_r_profit(position_factory) -> None:
    """Profit < 0.5 * risk must block trailing even if ATR trigger passes."""
    # entry=100, stop=90 → risk=10, 0.5xR = 5
    # Small ATR so legacy ATR trigger would otherwise pass:
    #   profit_atr = 4 / 2 = 2 >= trailing_stop_trigger_atr (2.0)
    # Profit 4 < 5, so the new risk-based lock must block.
    position = position_factory(current_stop_loss=Decimal(90))
    checker = TrailingStopChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(104),
        current_atr=Decimal(2),
    )

    assert action is None


def test_trailing_fires_at_half_r_profit(position_factory) -> None:
    """At exactly 0.5xR profit the profit-lock passes and trail fires."""
    # entry=100, stop=90 → risk=10, 0.5xR = 5
    # current_price=105 → profit=5 (lock boundary)
    # atr=2, profit_atr=2.5 > 2.0 trigger, new_sl = 105 - 1.5*2 = 102
    position = position_factory(current_stop_loss=Decimal(90))
    checker = TrailingStopChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(105),
        current_atr=Decimal(2),
    )

    assert action is not None
    assert action.action == PositionActionType.MOVE_STOP_LOSS
    assert action.new_stop_loss == Decimal(102)


def test_trailing_respects_min_profit_lock_override(position_factory) -> None:
    """A stricter min_profit_lock_r blocks a trail that would otherwise fire."""
    # entry=100, stop=90 → risk=10
    # Override lock to 2.0xR → required profit = 20, current profit = 15
    # ATR trigger still passes (profit_atr = 1.5 vs trigger 1.0), so the
    # only thing blocking is the stricter profit-lock override.
    config = PositionManagementConfigSchema(
        trailing_stop_trigger_atr=Decimal("1.0"),
        min_profit_lock_r=Decimal("2.0"),
    )
    position = position_factory(
        current_stop_loss=Decimal(90),
        management_config=config,
    )
    checker = TrailingStopChecker()

    action = checker.evaluate(
        position=position,
        current_price=Decimal(115),
        current_atr=Decimal(10),
    )

    assert action is None
