import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import OrderResponseSchema
from kavzi_trader.spine.state.account_store import AccountStore
from kavzi_trader.spine.state.order_store import OrderStore
from kavzi_trader.spine.state.position_store import PositionStore
from kavzi_trader.spine.state.schemas import OpenOrderSchema, ReconciliationResultSchema

logger = logging.getLogger(__name__)


class ReconciliationService:
    def __init__(
        self,
        exchange_client: BinanceClient,
        position_store: PositionStore,
        order_store: OrderStore,
        account_store: AccountStore,
    ) -> None:
        self._exchange = exchange_client
        self._positions = position_store
        self._orders = order_store
        self._account = account_store

    async def reconcile(self) -> ReconciliationResultSchema:
        logger.info("Starting state reconciliation with exchange")
        discrepancies: list[str] = []
        positions_synced = 0
        orders_synced = 0
        orders_removed = 0

        try:
            logger.debug("Reconciling account balance")
            await self._reconcile_account()
            logger.debug("Reconciling open orders")
            orders_synced, orders_removed = await self._reconcile_orders(discrepancies)
            logger.debug("Verifying protective orders")
            positions_synced = await self._verify_protective_orders(discrepancies)
        except Exception:
            logger.exception("Reconciliation failed")
            return ReconciliationResultSchema(
                success=False,
                discrepancies=discrepancies,
                positions_synced=positions_synced,
                orders_synced=orders_synced,
                orders_removed=orders_removed,
            )

        logger.info(
            "Reconciliation complete: %d discrepancies, %d orders synced, %d removed",
            len(discrepancies),
            orders_synced,
            orders_removed,
        )
        return ReconciliationResultSchema(
            success=True,
            discrepancies=discrepancies,
            positions_synced=positions_synced,
            orders_synced=orders_synced,
            orders_removed=orders_removed,
        )

    async def _reconcile_account(self) -> None:
        account_info = await self._exchange.get_account_info()

        total_usdt = Decimal(0)
        available_usdt = Decimal(0)
        locked_usdt = Decimal(0)

        for balance in account_info.get("balances", []):
            if balance["asset"] == "USDT":
                available_usdt = Decimal(balance["free"])
                locked_usdt = Decimal(balance["locked"])
                total_usdt = available_usdt + locked_usdt
                break

        await self._account.update_balance(
            total_balance=total_usdt,
            available_balance=available_usdt,
            locked_balance=locked_usdt,
        )
        logger.info("Account balance synced: %s USDT", total_usdt)

    async def _reconcile_orders(
        self,
        discrepancies: list[str],
    ) -> tuple[int, int]:
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

        return orders_synced, orders_removed

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

    async def _verify_protective_orders(self, discrepancies: list[str]) -> int:
        positions = await self._positions.get_all()
        verified_count = 0

        for position in positions:
            linked_orders = await self._orders.get_by_position(position.id)

            has_sl = any(
                o.order_type.value in ("STOP_LOSS", "STOP_LOSS_LIMIT")
                for o in linked_orders
            )
            has_tp = any(
                o.order_type.value in ("TAKE_PROFIT", "TAKE_PROFIT_LIMIT")
                for o in linked_orders
            )

            if not has_sl:
                msg = f"Position {position.id} missing stop-loss order"
                discrepancies.append(msg)
                logger.warning(
                    "Protective orders missing: %s has no stop-loss",
                    position.id,
                )
            if not has_tp:
                msg_tp = f"Position {position.id} missing take-profit order"
                discrepancies.append(msg_tp)
                logger.warning(
                    "Protective orders missing: %s has no take-profit",
                    position.id,
                )

            if has_sl and has_tp:
                verified_count += 1

        return verified_count
