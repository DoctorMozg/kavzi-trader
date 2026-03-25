import logging
from decimal import Decimal

from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class TrailingStopChecker:
    """Suggests a tighter stop loss once a trade moves strongly in profit."""

    def evaluate(
        self,
        position: PositionSchema,
        current_price: Decimal,
        current_atr: Decimal,
    ) -> PositionActionSchema | None:
        if current_atr <= 0:
            logger.warning(
                "ATR is %s for %s, trailing stop cannot function",
                current_atr, position.symbol,
            )
            return None

        if position.side == "LONG":
            profit = current_price - position.entry_price
        else:
            profit = position.entry_price - current_price

        if profit <= 0:
            return None

        profit_atr = profit / current_atr
        if profit_atr < Decimal("2.0"):
            return None

        trail_distance = (
            current_atr * position.management_config.trailing_stop_atr_multiplier
        )
        if position.side == "LONG":
            new_stop_loss = current_price - trail_distance
            if new_stop_loss <= position.current_stop_loss:
                return None
        else:
            new_stop_loss = current_price + trail_distance
            if new_stop_loss >= position.current_stop_loss:
                return None

        logger.debug(
            "Trailing stop triggered for %s: profit_atr=%s"
            " new_sl=%s old_sl=%s",
            position.symbol, profit_atr,
            new_stop_loss, position.current_stop_loss,
        )
        return PositionActionSchema(
            action=PositionActionType.MOVE_STOP_LOSS,
            new_stop_loss=new_stop_loss,
            reason="trailing_stop",
        )
