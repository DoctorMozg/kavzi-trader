import logging
from decimal import Decimal

from kavzi_trader.domain.position_action import PositionActionSchema
from kavzi_trader.domain.position_action_type import PositionActionType
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision

logger = logging.getLogger(__name__)


class PartialExitChecker:
    """Suggests taking partial profit when price reaches a target level."""

    def __init__(self, precision: SymbolPrecision | None = None) -> None:
        self._precision = precision

    def evaluate(
        self,
        position: PositionSchema,
        current_price: Decimal,
        current_atr: Decimal,
    ) -> PositionActionSchema | None:
        if position.partial_exit_done or position.take_profit is None:
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
        if progress < position.management_config.partial_exit_at_fraction:
            return None

        min_profit_atr = position.management_config.partial_exit_min_profit_atr
        # Use ATR at entry so volatility expansion after open can't shrink
        # profit/ATR below the threshold and suppress a valid partial exit.
        reference_atr = position.atr_at_entry or current_atr
        if reference_atr > 0 and min_profit_atr > 0:
            profit_atr = current_distance / reference_atr
            if profit_atr < min_profit_atr:
                logger.debug(
                    "Partial exit skipped for %s: profit_atr=%s < min=%s",
                    position.symbol,
                    profit_atr,
                    min_profit_atr,
                )
                return None

        exit_quantity = position.quantity * position.management_config.partial_exit_size
        if self._precision is not None:
            exit_quantity = self._tradable_exit(
                self._precision,
                position,
                exit_quantity,
            )
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

    @staticmethod
    def _tradable_exit(
        precision: SymbolPrecision,
        position: PositionSchema,
        quantity: Decimal,
    ) -> Decimal:
        """Floor to the lot step; zero when the exit or remainder is untradable."""
        rounded = precision.round_qty(position.symbol, quantity)
        remaining = position.quantity - rounded
        for qty in (rounded, remaining):
            if precision.check_qty(position.symbol, qty, reduce_only=True):
                logger.debug(
                    "Partial exit skipped for %s: exit_qty=%s remaining=%s "
                    "not tradable at exchange filters",
                    position.symbol,
                    rounded,
                    remaining,
                )
                return Decimal(0)
        return rounded
