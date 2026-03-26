import logging
from decimal import Decimal

from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class PartialExitChecker:
    """Suggests taking partial profit when price reaches a target level."""

    def evaluate(
        self,
        position: PositionSchema,
        current_price: Decimal,
    ) -> PositionActionSchema | None:
        if position.partial_exit_done:
            return None

        if position.side == "LONG":
            total_distance = position.take_profit - position.entry_price
            current_distance = current_price - position.entry_price
        else:
            total_distance = position.entry_price - position.take_profit
            current_distance = position.entry_price - current_price

        if total_distance <= 0 or current_distance <= 0:
            return None

        progress = current_distance / total_distance
        if progress < position.management_config.partial_exit_at_percent:
            return None

        exit_quantity = position.quantity * position.management_config.partial_exit_size
        if exit_quantity <= 0:
            return None

        logger.debug(
            "Partial exit triggered for %s: progress=%.1f%% exit_qty=%s",
            position.symbol,
            float(progress) * 100,
            exit_quantity,
        )
        return PositionActionSchema(
            action=PositionActionType.PARTIAL_EXIT,
            exit_quantity=exit_quantity,
            reason="partial_exit",
        )
