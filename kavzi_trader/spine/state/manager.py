import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.spine.state.account_store import AccountStore
from kavzi_trader.spine.state.config import RedisConfigSchema
from kavzi_trader.spine.state.order_store import OrderStore
from kavzi_trader.spine.state.position_store import PositionStore
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    OpenOrderSchema,
    PositionSchema,
    ReconciliationResultSchema,
)

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(
        self,
        redis_config: RedisConfigSchema,
        exchange_client: BinanceClient,
    ) -> None:
        self._exchange = exchange_client
        self._redis_client = RedisStateClient(redis_config)
        self._position_store = PositionStore(self._redis_client)
        self._order_store = OrderStore(self._redis_client)
        self._account_store = AccountStore(self._redis_client)

    @property
    def positions(self) -> PositionStore:
        return self._position_store

    @property
    def orders(self) -> OrderStore:
        return self._order_store

    @property
    def account(self) -> AccountStore:
        return self._account_store

    async def connect(self) -> None:
        await self._redis_client.connect()

    async def close(self) -> None:
        await self._redis_client.close()

    async def get_position(self, symbol: str) -> PositionSchema | None:
        return await self._position_store.get_by_symbol(symbol)

    async def get_all_positions(self) -> list[PositionSchema]:
        return await self._position_store.get_all()

    async def update_position(self, position: PositionSchema) -> None:
        await self._position_store.save(position)

    async def remove_position(self, position_id: str) -> None:
        await self._position_store.delete(position_id)

    async def get_open_orders(self, symbol: str | None = None) -> list[OpenOrderSchema]:
        if symbol:
            return await self._order_store.get_by_symbol(symbol)
        return await self._order_store.get_all()

    async def save_order(self, order: OpenOrderSchema) -> None:
        await self._order_store.save(order)

    async def remove_order(self, order_id: str) -> None:
        await self._order_store.delete(order_id)

    async def get_account_state(self) -> AccountStateSchema | None:
        return await self._account_store.get()

    async def get_current_drawdown(self) -> Decimal:
        return await self._account_store.get_drawdown()

    async def get_current_price(self, symbol: str) -> Decimal:
        ticker = await self._exchange.get_ticker(symbol)
        return ticker.last_price

    async def reconcile_with_exchange(self) -> ReconciliationResultSchema:
        from kavzi_trader.spine.state.reconciliation import ReconciliationService

        service = ReconciliationService(
            exchange_client=self._exchange,
            position_store=self._position_store,
            order_store=self._order_store,
            account_store=self._account_store,
        )
        return await service.reconcile()
