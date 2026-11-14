import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.domain.order_enums import OrderSide, OrderType
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.spine.execution.close_recorder import PositionCloseRecorder
from kavzi_trader.spine.execution.event_recorder import ExecutionEventRecorder
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class EmergencyCloser:
    """Market-closes a position whose protection could not be established."""

    def __init__(
        self,
        exchange: BinanceClient,
        state_manager: StateManager,
        events: ExecutionEventRecorder,
        close_recorder: PositionCloseRecorder | None,
    ) -> None:
        self._exchange = exchange
        self._state = state_manager
        self._events = events
        self._close_recorder = close_recorder

    async def close(self, position: PositionSchema) -> None:
        close_side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        exit_price: Decimal | None = None
        try:
            order_response = await self._exchange.create_order(
                symbol=position.symbol,
                side=close_side,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                reduce_only=True,
            )
            exit_price = order_response.effective_fill_price
            await self._state.remove_position(position.id)
            logger.warning(
                "Emergency-closed position %s for %s",
                position.id,
                position.symbol,
            )
        except Exception:
            logger.exception(
                "CRITICAL: Emergency close FAILED for position %s — "
                "manual intervention required",
                position.id,
            )
        await self._events.record(
            aggregate_id=position.id,
            aggregate_type=AggregateType.POSITIONS,
            event_type="emergency_close",
            data={"symbol": position.symbol, "reason": "protective_order_failure"},
        )
        if exit_price is not None and self._close_recorder is not None:
            try:
                await self._close_recorder.record_position_close(
                    position,
                    "Emergency close",
                    exit_price,
                )
            except Exception:
                logger.exception(
                    "Failed to report emergency close for %s",
                    position.symbol,
                )
