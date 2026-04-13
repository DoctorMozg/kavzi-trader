import logging
from decimal import Decimal

from kavzi_trader.spine.position.break_even import BreakEvenMover
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.position.time_exit import TimeExitChecker
from kavzi_trader.spine.position.trailing import TrailingStopChecker
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class PositionManager:
    """Coordinates position management decisions for a single open position."""

    def __init__(
        self,
        break_even: BreakEvenMover,
        trailing: TrailingStopChecker,
        partial_exit: PartialExitChecker,
        time_exit: TimeExitChecker,
    ) -> None:
        self._break_even = break_even
        self._trailing = trailing
        self._partial_exit = partial_exit
        self._time_exit = time_exit

    async def evaluate_position(
        self,
        position: PositionSchema,
        current_price: Decimal,
        current_atr: Decimal,
        mark_price: Decimal | None = None,
        liquidation_emergency_percent: Decimal = Decimal("5.0"),
    ) -> list[PositionActionSchema]:
        logger.debug(
            "Evaluating position %s %s: price=%s atr=%s mark=%s",
            position.id,
            position.symbol,
            current_price,
            current_atr,
            mark_price,
        )

        price_for_liq = mark_price if mark_price is not None else current_price
        if position.liquidation_price is not None and position.liquidation_price > 0:
            liq_dist = abs(price_for_liq - position.liquidation_price)
            entry_to_liq = abs(position.entry_price - position.liquidation_price)
            if entry_to_liq > 0:
                dist_pct = (liq_dist / entry_to_liq) * Decimal(100)
                if dist_pct <= liquidation_emergency_percent:
                    logger.warning(
                        "LIQUIDATION PROXIMITY: position %s %s is %.1f%% "
                        "from liquidation (mark=%s liq=%s)",
                        position.id,
                        position.symbol,
                        float(dist_pct),
                        price_for_liq,
                        position.liquidation_price,
                    )
                    return [
                        PositionActionSchema(
                            action=PositionActionType.FULL_EXIT,
                            reason="Emergency: near liquidation price",
                        ),
                    ]

        if position.side == "LONG" and current_price <= position.current_stop_loss:
            logger.warning(
                "STOP-LOSS BREACHED: position %s %s LONG price=%s <= sl=%s",
                position.id,
                position.symbol,
                current_price,
                position.current_stop_loss,
            )
            return [
                PositionActionSchema(
                    action=PositionActionType.FULL_EXIT,
                    reason="Stop-loss breached",
                ),
            ]
        if position.side == "SHORT" and current_price >= position.current_stop_loss:
            logger.warning(
                "STOP-LOSS BREACHED: position %s %s SHORT price=%s >= sl=%s",
                position.id,
                position.symbol,
                current_price,
                position.current_stop_loss,
            )
            return [
                PositionActionSchema(
                    action=PositionActionType.FULL_EXIT,
                    reason="Stop-loss breached",
                ),
            ]

        if current_atr <= 0:
            logger.warning(
                "ATR is %s for %s, trailing stop and break-even cannot function",
                current_atr,
                position.symbol,
            )

        time_exit_action = self._time_exit.evaluate(position)
        if time_exit_action:
            return [time_exit_action]

        actions: list[PositionActionSchema] = []

        move_sl_action = self._trailing.evaluate(position, current_price, current_atr)
        if move_sl_action is None:
            move_sl_action = self._break_even.evaluate(
                position,
                current_price,
                current_atr,
            )
        if move_sl_action is not None:
            actions.append(move_sl_action)

        # Invariant: never emit MOVE_STOP_LOSS and PARTIAL_EXIT in the same
        # cycle. The executor's partial-exit path cancels all linked orders
        # and re-places a stop at position.current_stop_loss (the OLD value),
        # which would silently undo the protective stop move. Defer the
        # partial exit one tick; it will re-trigger once the new SL is live.
        if move_sl_action is None:
            partial_exit_action = self._partial_exit.evaluate(
                position,
                current_price,
                current_atr,
            )
            if partial_exit_action:
                actions.append(partial_exit_action)
        else:
            logger.info(
                "Deferring partial_exit for %s: stop-loss move preferred this cycle",
                position.symbol,
            )

        logger.debug(
            "Position %s evaluation: %d actions",
            position.id,
            len(actions),
        )
        return actions
