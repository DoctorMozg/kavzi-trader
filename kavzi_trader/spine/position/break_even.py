import logging
from decimal import Decimal

from kavzi_trader.commons.time_utility import normalize_datetime_to_utc, utc_now
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

        min_hold_s = position.management_config.break_even_min_hold_s
        if min_hold_s > 0:
            opened_at = normalize_datetime_to_utc(position.opened_at)
            age_s = (utc_now() - opened_at).total_seconds()
            if age_s < min_hold_s:
                logger.debug(
                    "Break-even skipped for %s: position age %.0fs < min_hold %ds",
                    position.symbol,
                    age_s,
                    min_hold_s,
                )
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

        buffer = current_atr * position.management_config.break_even_buffer_atr
        if position.side == "LONG":
            new_stop_loss = position.entry_price + buffer
        else:
            new_stop_loss = position.entry_price - buffer

        if position.side == "LONG" and new_stop_loss <= position.current_stop_loss:
            return None
        if position.side == "SHORT" and new_stop_loss >= position.current_stop_loss:
            return None

        logger.debug(
            "Break-even triggered for %s: profit_atr=%s trigger=%s "
            "new_sl=%s (entry=%s buffer=%s)",
            position.symbol,
            profit_atr,
            trigger_atr,
            new_stop_loss,
            position.entry_price,
            buffer,
        )
        return PositionActionSchema(
            action=PositionActionType.MOVE_STOP_LOSS,
            new_stop_loss=new_stop_loss,
            reason="break_even",
        )
