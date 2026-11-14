import logging

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.order_enums import OrderStatus
from kavzi_trader.domain.order_response import OrderResponseSchema
from kavzi_trader.spine.execution.fill_handler import FillHandler
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.schemas import PendingEntrySchema

logger = logging.getLogger(__name__)


class PendingEntryManager:
    """Tracks resting entry limits and sweeps them for fill or expiry."""

    def __init__(
        self,
        exchange: BinanceClient,
        state_manager: StateManager,
        fill_handler: FillHandler,
        expiry_ms: int,
    ) -> None:
        self._exchange = exchange
        self._state = state_manager
        self._fill_handler = fill_handler
        self._expiry_ms = expiry_ms

    async def register(
        self,
        decision: DecisionMessageSchema,
        order_response: OrderResponseSchema,
    ) -> None:
        """Persist a resting pullback entry for the async sweep to manage."""
        entry = PendingEntrySchema(
            order_id=str(order_response.order_id),
            symbol=decision.symbol,
            decision_json=decision.model_dump_json(),
            expires_at_ms=decision.created_at_ms + self._expiry_ms,
        )
        try:
            await self._state.save_pending_entry(entry)
        except Exception:
            logger.exception(
                "Failed to persist pending entry %s for %s; the resting limit "
                "will rely on reconciliation instead",
                entry.order_id,
                decision.symbol,
                extra={"decision_id": decision.decision_id},
            )
            return
        logger.info(
            "Registered pending PULLBACK entry %s for %s, expires_at_ms=%s",
            entry.order_id,
            decision.symbol,
            entry.expires_at_ms,
            extra={"decision_id": decision.decision_id, "symbol": decision.symbol},
        )

    async def sweep(self, now_ms: int) -> None:
        """Protect filled entries and cancel expired ones.

        Each entry is polled independently so one bad order cannot stall the
        others.
        """
        entries = await self._state.list_pending_entries()
        for entry in entries:
            try:
                await self._process(entry, now_ms)
            except Exception:
                logger.exception(
                    "Failed to process pending entry %s for %s",
                    entry.order_id,
                    entry.symbol,
                )

    async def _process(self, entry: PendingEntrySchema, now_ms: int) -> None:
        order = await self._exchange.get_order(
            symbol=entry.symbol,
            order_id=int(entry.order_id),
        )
        if order.status == OrderStatus.FILLED:
            decision = DecisionMessageSchema.model_validate_json(entry.decision_json)
            await self._fill_handler.on_order_filled(decision, order)
            await self._state.remove_pending_entry(entry.order_id)
            logger.info(
                "Pending PULLBACK entry %s filled for %s; position opened",
                entry.order_id,
                entry.symbol,
                extra={"symbol": entry.symbol},
            )
            return
        if order.status == OrderStatus.NEW:
            if now_ms >= entry.expires_at_ms:
                await self._expire(entry)
            return
        if order.status == OrderStatus.PARTIALLY_FILLED:
            # Leave partial fills alone: cancelling would orphan the filled
            # portion unprotected. Let it fill fully or be handled by the
            # reconciler on the next pass.
            return
        # Terminal non-filled status (CANCELED / EXPIRED / REJECTED): the
        # order has left the book, so stop tracking it.
        await self._state.remove_pending_entry(entry.order_id)
        logger.info(
            "Pending entry %s for %s ended with status %s; dropped from tracking",
            entry.order_id,
            entry.symbol,
            order.status.value,
            extra={"symbol": entry.symbol},
        )

    async def _expire(self, entry: PendingEntrySchema) -> None:
        try:
            await self._exchange.cancel_order(
                symbol=entry.symbol,
                order_id=int(entry.order_id),
            )
        except Exception:
            logger.exception(
                "Failed to cancel expired pending entry %s for %s",
                entry.order_id,
                entry.symbol,
            )
        await self._state.remove_pending_entry(entry.order_id)
        logger.info(
            "Expired unfilled PULLBACK entry %s for %s and cancelled the limit",
            entry.order_id,
            entry.symbol,
            extra={"symbol": entry.symbol},
        )
