import logging

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.execution_result import ExecutionResultSchema
from kavzi_trader.domain.order_enums import OrderStatus
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.spine.execution.fill_handler import FillHandler
from kavzi_trader.spine.execution.pending_entries import PendingEntryManager
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class UnfilledEntryResolver:
    """Settles an entry that did not fill within the monitor timeout."""

    def __init__(
        self,
        exchange: ExchangeClient,
        state_manager: StateManager,
        fill_handler: FillHandler,
        pending_entries: PendingEntryManager,
    ) -> None:
        self._exchange = exchange
        self._state = state_manager
        self._fill_handler = fill_handler
        self._pending_entries = pending_entries

    async def resolve(
        self,
        decision: DecisionMessageSchema,
        order_response: OrderResponseSchema,
        monitored: OrderResponseSchema | None,
    ) -> ExecutionResultSchema:
        """Cancel a timed-out entry and protect whatever filled in the meantime."""
        final = monitored
        if final is None:
            final = await self._cancel_entry(decision.symbol, order_response.order_id)

        if final is None or final.status in {
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.PENDING_CANCEL,
        }:
            # Order state unknown or still live: track it so a late fill is protected.
            await self._pending_entries.register(decision, order_response)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=str(order_response.order_id),
                status="SUBMITTED",
                executed_qty=order_response.executed_qty,
                executed_price=order_response.price,
                error_message=None,
                needs_reconciliation=True,
            )

        if final.executed_qty > 0:
            await self._fill_handler.on_order_filled(decision, final)
            return ExecutionResultSchema(
                decision_id=decision.decision_id,
                order_id=str(final.order_id),
                status="FILLED",
                executed_qty=final.executed_qty,
                executed_price=final.effective_fill_price,
                error_message=None,
                needs_reconciliation=False,
            )

        try:
            await self._state.remove_order(str(final.order_id))
        except Exception:
            logger.exception(
                "Failed to remove dead entry order %s from state",
                final.order_id,
            )
        logger.info(
            "Entry order %s for %s ended unfilled: status=%s",
            final.order_id,
            decision.symbol,
            final.status.value,
            extra={"decision_id": decision.decision_id, "symbol": decision.symbol},
        )
        return ExecutionResultSchema(
            decision_id=decision.decision_id,
            order_id=str(final.order_id),
            status="EXPIRED",
            executed_qty=None,
            executed_price=None,
            error_message=f"entry not filled; order {final.status.value}",
            needs_reconciliation=False,
        )

    async def _cancel_entry(
        self,
        symbol: str,
        order_id: int,
    ) -> OrderResponseSchema | None:
        """Cancel the entry; if cancel fails (e.g. filled meanwhile), read its state."""
        try:
            return await self._exchange.cancel_order(symbol=symbol, order_id=order_id)
        except Exception:
            logger.exception(
                "Failed to cancel timed-out entry %s for %s; checking order state",
                order_id,
                symbol,
            )
        try:
            return await self._exchange.get_order(symbol=symbol, order_id=order_id)
        except Exception:
            logger.exception(
                "Failed to read timed-out entry %s for %s",
                order_id,
                symbol,
            )
            return None
