import logging
from decimal import Decimal

from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class ScaleInChecker:
    """Suggests adding size after a profitable trade retraces near entry."""

    def evaluate(
        self,
        position: PositionSchema,
        current_price: Decimal,
        current_atr: Decimal,
    ) -> PositionActionSchema | None:
        if not position.management_config.scale_in_allowed:
            return None

        if current_atr <= 0:
            return None

        if position.side == "LONG":
            profit = current_price - position.entry_price
        else:
            profit = position.entry_price - current_price

        if profit <= 0:
            return None

        profit_atr = profit / current_atr
        retrace_limit = Decimal("0.5")
        if profit_atr > retrace_limit:
            return None

        scale_multiplier = position.management_config.scale_in_max_multiplier
        scale_in_quantity = position.quantity * (scale_multiplier - Decimal("1.0"))
        if scale_in_quantity <= 0:
            return None

        logger.debug(
            "Scale-in triggered for %s: profit_atr=%s scale_qty=%s",
            position.symbol,
            profit_atr,
            scale_in_quantity,
        )
        return PositionActionSchema(
            action=PositionActionType.SCALE_IN,
            scale_in_quantity=scale_in_quantity,
            reason="scale_in_retrace",
        )
