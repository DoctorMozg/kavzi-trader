import logging
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import OrderResponseSchema
from kavzi_trader.spine.state.account_store import AccountStore
from kavzi_trader.spine.state.order_store import OrderStore
from kavzi_trader.spine.state.position_store import PositionStore
from kavzi_trader.spine.state.schemas import (
    OpenOrderSchema,
    PositionSchema,
    ReconciliationResultSchema,
)

logger = logging.getLogger(__name__)


class ProtectiveOrderPlacer(Protocol):
    """Re-places missing protective legs (SL, TP) for an existing position.

    The reconciler calls this once per position that is missing one or both
    legs. Implementations MUST only place the legs whose flag is True and MUST
    NOT trigger emergency-close on failure: the reconciler already classifies
    unplaceable legs as unrecoverable, and auto-closing on top of that during
    a periodic sweep is policy overreach.
    """

    async def place(
        self,
        position: PositionSchema,
        *,
        place_stop_loss: bool,
        place_take_profit: bool,
    ) -> None: ...


class _OrderReconciliationCounts(BaseModel):
    synced: int
    removed: int
    model_config = ConfigDict(frozen=True)


class _ProtectiveOrderRecovery(BaseModel):
    verified: int
    unrecoverable: list[str]
    model_config = ConfigDict(frozen=True)


class ReconciliationService:
    def __init__(
        self,
        exchange_client: BinanceClient,
        position_store: PositionStore,
        order_store: OrderStore,
        account_store: AccountStore,
        protective_order_placer: ProtectiveOrderPlacer | None = None,
    ) -> None:
        self._exchange = exchange_client
        self._positions = position_store
        self._orders = order_store
        self._account = account_store
        self._protective_order_placer = protective_order_placer

    async def reconcile(self) -> ReconciliationResultSchema:
        logger.info("Starting state reconciliation with exchange")
        discrepancies: list[str] = []
        positions_synced = 0
        orders_synced = 0
        orders_removed = 0
        unrecoverable: list[str] = []

        try:
            logger.debug("Reconciling account balance")
            await self._reconcile_account()
            logger.debug("Reconciling open orders")
            order_counts = await self._reconcile_orders(discrepancies)
            orders_synced = order_counts.synced
            orders_removed = order_counts.removed
            logger.debug("Verifying protective orders")
            recovery = await self._verify_protective_orders(discrepancies)
            positions_synced = recovery.verified
            unrecoverable = recovery.unrecoverable
        except Exception:
            logger.exception(
                "Reconciliation failed",
                extra={
                    "discrepancies_count": len(discrepancies),
                    "positions_synced": positions_synced,
                    "orders_synced": orders_synced,
                    "orders_removed": orders_removed,
                },
            )
            return ReconciliationResultSchema(
                success=False,
                discrepancies=discrepancies,
                positions_synced=positions_synced,
                orders_synced=orders_synced,
                orders_removed=orders_removed,
            )

        success = len(unrecoverable) == 0
        if not success:
            logger.error(
                "Reconciliation finished with %d unrecoverable protective-order issues",
                len(unrecoverable),
            )
        logger.info(
            "Reconciliation complete: %d discrepancies, %d orders synced, %d removed",
            len(discrepancies),
            orders_synced,
            orders_removed,
        )
        return ReconciliationResultSchema(
            success=success,
            discrepancies=discrepancies,
            positions_synced=positions_synced,
            orders_synced=orders_synced,
            orders_removed=orders_removed,
        )

    async def _reconcile_account(self) -> None:
        account_info = await self._exchange.get_account_info()

        total_usdt = Decimal(account_info.get("totalWalletBalance", "0"))
        available_usdt = Decimal(account_info.get("availableBalance", "0"))
        unrealized_pnl = Decimal(
            account_info.get("totalUnrealizedProfit", "0"),
        )
        locked_usdt = total_usdt - available_usdt

        await self._account.update_balance(
            total_balance=total_usdt,
            available_balance=available_usdt,
            locked_balance=locked_usdt,
            unrealized_pnl=unrealized_pnl,
        )
        logger.info(
            "Account balance synced: total=%s available=%s unrealized=%s",
            total_usdt,
            available_usdt,
            unrealized_pnl,
        )

    async def _reconcile_orders(
        self,
        discrepancies: list[str],
    ) -> _OrderReconciliationCounts:
        exchange_orders = await self._exchange.get_open_orders()
        local_orders = await self._orders.get_all()

        exchange_order_ids = {str(o.order_id) for o in exchange_orders}
        local_order_ids = {o.order_id for o in local_orders}

        orders_synced = 0
        orders_removed = 0

        for exchange_order in exchange_orders:
            if str(exchange_order.order_id) not in local_order_ids:
                discrepancies.append(
                    f"Unknown order found on exchange: {exchange_order.order_id}",
                )
                await self._import_order_from_exchange(exchange_order)
                orders_synced += 1

        for local_order in local_orders:
            if local_order.order_id not in exchange_order_ids:
                discrepancies.append(
                    f"Stale order in local state: {local_order.order_id}",
                )
                await self._orders.delete(local_order.order_id)
                orders_removed += 1

        return _OrderReconciliationCounts(
            synced=orders_synced,
            removed=orders_removed,
        )

    async def _import_order_from_exchange(
        self,
        exchange_order: OrderResponseSchema,
    ) -> None:
        order = OpenOrderSchema(
            order_id=str(exchange_order.order_id),
            symbol=exchange_order.symbol,
            side=exchange_order.side,
            order_type=exchange_order.type,
            price=exchange_order.price,
            quantity=exchange_order.orig_qty,
            executed_qty=exchange_order.executed_qty,
            status=exchange_order.status,
            linked_position_id=None,
            created_at=exchange_order.transact_time,
        )
        await self._orders.save(order)
        logger.info("Imported order %s from exchange", order.order_id)

    async def _verify_protective_orders(
        self,
        discrepancies: list[str],
    ) -> _ProtectiveOrderRecovery:
        positions = await self._positions.get_all()
        verified_count = 0
        unrecoverable: list[str] = []

        for position in positions:
            linked_orders = await self._orders.get_by_position(position.id)

            has_sl = any(
                o.order_type.value in ("STOP", "STOP_MARKET") for o in linked_orders
            )
            has_tp = any(
                o.order_type.value in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET")
                for o in linked_orders
            )

            if has_sl and has_tp:
                verified_count += 1
                continue

            # Single placer call per position with explicit leg selection. Prior
            # versions invoked the placer once per missing leg, which combined
            # with a placer that always placed both legs produced duplicate
            # reduceOnly orders on the exchange.
            missing: list[str] = []
            if not has_sl:
                missing.append("stop-loss")
            if not has_tp:
                missing.append("take-profit")

            outcomes = await self._attempt_protective_recovery(
                position=position,
                missing=missing,
                place_stop_loss=not has_sl,
                place_take_profit=not has_tp,
            )
            discrepancies.extend(outcomes)
            unrecoverable.extend(o for o in outcomes if "unrecoverable" in o)

        return _ProtectiveOrderRecovery(
            verified=verified_count,
            unrecoverable=unrecoverable,
        )

    async def _attempt_protective_recovery(
        self,
        position: PositionSchema,
        missing: list[str],
        *,
        place_stop_loss: bool,
        place_take_profit: bool,
    ) -> list[str]:
        """Re-place the missing legs and return one discrepancy per leg.

        Fails closed (CRITICAL log + per-leg unrecoverable entries) when no
        placer is configured. On placer exception all requested legs are marked
        unrecoverable — the reconciler cannot tell which leg partially landed,
        so it treats the whole attempt as failed and leaves auto-close policy
        to the operator.
        """
        missing_label = " and ".join(missing)

        if self._protective_order_placer is None:
            logger.critical(
                "Position %s missing %s and no protective_order_placer "
                "configured — unrecoverable",
                position.id,
                missing_label,
                extra={"position_id": position.id, "symbol": position.symbol},
            )
            return [
                f"Position {position.id} missing {leg} order "
                "(unrecoverable: no placer configured)"
                for leg in missing
            ]

        try:
            await self._protective_order_placer.place(
                position,
                place_stop_loss=place_stop_loss,
                place_take_profit=place_take_profit,
            )
        except Exception as exc:
            logger.exception(
                "Failed to re-place %s for position %s; unrecoverable",
                missing_label,
                position.id,
                extra={"position_id": position.id, "symbol": position.symbol},
            )
            return [
                f"Position {position.id} missing {leg} order (unrecoverable: {exc})"
                for leg in missing
            ]

        logger.warning(
            "Recovered missing %s for position %s via re-placement",
            missing_label,
            position.id,
            extra={"position_id": position.id, "symbol": position.symbol},
        )
        return [
            f"Position {position.id} missing {leg} order (recovered)" for leg in missing
        ]
