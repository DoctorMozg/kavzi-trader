import logging
from decimal import Decimal

from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class BreakEvenMover:
    """Moves the stop loss to the entry price after enough profit."""

    def evaluate(  # noqa: PLR0911
        self,
        position: PositionSchema,
        current_price: Decimal,
        current_atr: Decimal,
    ) -> PositionActionSchema | None:
        if current_atr <= 0:
            logger.warning(
                "ATR is %s for %s, break-even cannot function",
                current_atr,
                position.symbol,
            )
            return None
        if position.stop_loss_moved_to_breakeven:
            return None

        if position.side == "LONG":
            profit = current_price - position.entry_price
        else:
            profit = position.entry_price - current_price

        if profit <= 0:
            return None

        profit_atr = profit / current_atr
        trigger_atr = position.management_config.break_even_trigger_atr

        if profit_atr < trigger_atr:
            return None

        new_stop_loss = position.entry_price
        if position.side == "LONG" and new_stop_loss <= position.current_stop_loss:
            return None
        if position.side == "SHORT" and new_stop_loss >= position.current_stop_loss:
            return None

        logger.debug(
            "Break-even triggered for %s: profit_atr=%s trigger=%s new_sl=%s",
            position.symbol,
            profit_atr,
            trigger_atr,
            new_stop_loss,
        )
        return PositionActionSchema(
            action=PositionActionType.MOVE_STOP_LOSS,
            new_stop_loss=new_stop_loss,
            reason="break_even",
        )
