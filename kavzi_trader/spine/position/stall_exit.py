import logging
from decimal import Decimal

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class StallExitChecker:
    """Exits positions that stop progressing toward TP without hitting SL.

    After ``stall_check_after_hours`` have elapsed, if the position's net
    profit distance toward the take-profit is below ``stall_min_progress_atr``
    ATR units, the setup has failed silently and the capital should be freed.

    Uses atr_at_entry as the reference so volatility expansion after open
    cannot artificially suppress the progress signal.
    """

    def evaluate(
        self,
        position: PositionSchema,
        current_price: Decimal,
        current_atr: Decimal,
    ) -> PositionActionSchema | None:
        config = position.management_config
        elapsed_s = (utc_now() - position.opened_at).total_seconds()
        threshold_s = config.stall_check_after_hours * 3600
        if elapsed_s < threshold_s:
            return None

        if position.side == "LONG":
            net_progress = current_price - position.entry_price
        else:
            net_progress = position.entry_price - current_price

        if net_progress <= 0:
            # No progress at all — stall exit (trailing could have caught this
            # but we're the safety net for slow-decay setups)
            logger.debug(
                "Stall exit triggered for %s: no net progress after %.1fh",
                position.symbol,
                elapsed_s / 3600,
            )
            return PositionActionSchema(
                action=PositionActionType.FULL_EXIT,
                reason="stall_exit",
            )

        reference_atr = position.atr_at_entry or current_atr
        if reference_atr <= 0:
            return None

        progress_atr = net_progress / reference_atr
        if progress_atr < config.stall_min_progress_atr:
            logger.debug(
                "Stall exit triggered for %s: progress_atr=%s < min=%s after %.1fh",
                position.symbol,
                progress_atr,
                config.stall_min_progress_atr,
                elapsed_s / 3600,
            )
            return PositionActionSchema(
                action=PositionActionType.FULL_EXIT,
                reason="stall_exit",
            )

        return None
