from decimal import Decimal

from kavzi_trader.spine.position.break_even import BreakEvenMover
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.scaling import ScaleInChecker
from kavzi_trader.spine.position.time_exit import TimeExitChecker
from kavzi_trader.spine.position.trailing import TrailingStopChecker
from kavzi_trader.spine.state.schemas import PositionSchema


class PositionManager:
    """Coordinates position management decisions for a single open position."""

    def __init__(
        self,
        break_even: BreakEvenMover,
        trailing: TrailingStopChecker,
        partial_exit: PartialExitChecker,
        time_exit: TimeExitChecker,
        scaling: ScaleInChecker,
    ) -> None:
        self._break_even = break_even
        self._trailing = trailing
        self._partial_exit = partial_exit
        self._time_exit = time_exit
        self._scaling = scaling

    async def evaluate_position(
        self,
        position: PositionSchema,
        current_price: Decimal,
        current_atr: Decimal,
    ) -> list[PositionActionSchema]:
        time_exit_action = self._time_exit.evaluate(position)
        if time_exit_action:
            return [time_exit_action]

        actions: list[PositionActionSchema] = []

        trailing_action = self._trailing.evaluate(position, current_price, current_atr)
        if trailing_action:
            actions.append(trailing_action)
        else:
            break_even_action = self._break_even.evaluate(
                position,
                current_price,
                current_atr,
            )
            if break_even_action:
                actions.append(break_even_action)

        partial_exit_action = self._partial_exit.evaluate(position, current_price)
        if partial_exit_action:
            actions.append(partial_exit_action)

        scale_in_action = self._scaling.evaluate(position, current_price, current_atr)
        if scale_in_action:
            actions.append(scale_in_action)

        return actions
