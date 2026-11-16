import logging
from decimal import Decimal

from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.spine.execution.event_recorder import ExecutionEventRecorder
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class DrawdownCircuitBreaker:
    """Reports when account drawdown calls for closing every position.

    The trip event fires once per breach; it re-arms when drawdown recovers
    below the threshold. While tripped, check() stays True so a close that
    failed on one position is retried on the next tick.
    """

    def __init__(
        self,
        close_all_percent: Decimal,
        state_manager: StateManager,
        events: ExecutionEventRecorder,
    ) -> None:
        self._close_all_percent = close_all_percent
        self._state = state_manager
        self._events = events
        self._tripped = False

    async def check(self, open_positions: int) -> bool:
        try:
            drawdown = await self._state.get_current_drawdown()
        except Exception:
            logger.exception("Drawdown unavailable; circuit breaker not evaluated")
            return False
        if drawdown < self._close_all_percent:
            if self._tripped:
                logger.info(
                    "Drawdown %s%% recovered; circuit breaker re-armed", drawdown
                )
            self._tripped = False
            return False
        if not self._tripped:
            self._tripped = True
            logger.critical(
                "Drawdown %s%% reached close-all threshold %s%%; closing %d positions",
                drawdown,
                self._close_all_percent,
                open_positions,
                extra={"drawdown_percent": str(drawdown)},
            )
            await self._events.record(
                aggregate_id="drawdown_circuit_breaker",
                aggregate_type=AggregateType.SYSTEM,
                event_type="drawdown_close_all",
                data={
                    "drawdown_percent": float(drawdown),
                    "threshold_percent": float(self._close_all_percent),
                    "open_positions": open_positions,
                },
            )
        return True
