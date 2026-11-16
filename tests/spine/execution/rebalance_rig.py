from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock

from redis.asyncio import Redis

from kavzi_trader.commons.sim_clock import SimClock
from kavzi_trader.domain.order_enums import OrderType
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.state_schemas import (
    PositionSchema,
)
from kavzi_trader.infra.in_memory_redis import InMemoryRedis
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.infra.redis_config import RedisConfigSchema
from kavzi_trader.orchestrator.loops.decision_queue import DECISION_QUEUE_KEY
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.paper.costs_schema import PaperCostsSchema
from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.paper.sim_market_feed import SimMarketFeed
from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)

SYMBOL = "BTCUSDT"
# 2021-01-01T00:00Z: any wall-clock read left in the spine shows up as 2026.
SIM_START_MS = 1_609_459_200_000
INTENT_TTL_MS = 3_600_000


class Rig:
    """Real loop, engine, state and paper exchange over an in-memory Redis."""

    def __init__(
        self,
        precision: SymbolPrecision | None = None,
        redis: InMemoryRedis | None = None,
        symbols: tuple[str, ...] = (SYMBOL,),
    ) -> None:
        self.clock = SimClock(SIM_START_MS)
        self.feed = SimMarketFeed()
        self._symbols = symbols
        self.redis = redis or InMemoryRedis()
        self.redis_client = RedisStateClient(
            RedisConfigSchema(), cast("Redis", self.redis)
        )
        self.price = Decimal(100)
        self.events = AsyncMock()
        self.close_recorder = AsyncMock()
        self.exchange = PaperExchangeClient(
            initial_balance_usdt=Decimal(1000),
            costs=PaperCostsSchema(
                taker_fee_rate=Decimal(0), maker_fee_rate=Decimal(0)
            ),
            clock=self.clock,
            market_feed=self.feed,
        )
        self.state = StateManager(self.redis_client, self.exchange, self.clock)
        self.exchange.set_account_store(self.state.account)
        self.engine = ExecutionEngine(
            exchange=self.exchange,
            state_manager=self.state,
            risk_validator=DynamicRiskValidator(RiskConfigSchema()),
            staleness_checker=StalenessChecker(ExecutionConfigSchema(), self.clock),
            translator=DecisionTranslator(),
            monitor=OrderMonitor(self.exchange, 1, self.clock),
            event_store=self.events,
            leverage=1,
            close_recorder=self.close_recorder,
            precision=precision,
            clock=self.clock,
        )
        self.loop = ExecutionLoop(
            redis_client=self.redis_client,
            engine=self.engine,
            state_manager=self.state,
            clock=self.clock,
        )

    @property
    def price(self) -> Decimal:
        return self._price

    @price.setter
    def price(self, value: Decimal) -> None:
        self._price = value
        for symbol in self._symbols:
            self.feed.set_price(symbol, value)

    async def deliver(self, raw: str) -> None:
        await self.redis.lpush(DECISION_QUEUE_KEY, raw)
        assert await self.loop.step() == 1

    async def position(self) -> PositionSchema | None:
        return await self.state.get_position(SYMBOL)

    async def stop_orders(self) -> list[tuple[Decimal, Decimal]]:
        """(quantity, stop price) of live exchange-side stop orders."""
        return [
            (o.orig_qty, o.stop_price or Decimal(0))
            for o in await self.exchange.get_open_orders(SYMBOL)
            if o.type == OrderType.STOP_MARKET
        ]


def make_intent(
    intent_id: str,
    weight: str,
    expires_at_ms: int | None = None,
) -> TargetWeightIntentSchema:
    return TargetWeightIntentSchema(
        strategy="trend",
        intent_id=intent_id,
        symbol=SYMBOL,
        target_weight=Decimal(weight),
        disaster_stop_pct=Decimal("0.3"),
        created_at_ms=SIM_START_MS,
        expires_at_ms=expires_at_ms or SIM_START_MS + INTENT_TTL_MS,
    )
