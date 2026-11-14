import logging
from decimal import Decimal

from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.ui.recorder import UiEventRecorder

logger = logging.getLogger(__name__)


class PositionCloseReporter:
    """Forwards position closes to the UI recorder; a UI failure never propagates."""

    def __init__(self, recorder: UiEventRecorder | None, loop_name: str) -> None:
        self._recorder = recorder
        self._loop_name = loop_name

    async def report(
        self,
        position: PositionSchema,
        close_reason: str,
        exit_price: Decimal,
    ) -> None:
        if self._recorder is None:
            return
        try:
            await self._recorder.record_position_close(
                position,
                close_reason,
                exit_price,
            )
        except Exception:
            logger.exception(
                "Failed to report position close for %s",
                position.symbol,
                extra={
                    "loop": self._loop_name,
                    "position_id": position.id,
                    "symbol": position.symbol,
                    "close_reason": close_reason,
                },
            )
