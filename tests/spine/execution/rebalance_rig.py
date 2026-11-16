from decimal import Decimal
from unittest.mock import AsyncMock, patch

from kavzi_trader.api.common.models import TickerSchema
from kavzi_trader.domain.order_enums import OrderType
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.state_schemas import (
    PositionSchema,
)
from kavzi_trader.infra.redis_config import RedisConfigSchema
from kavzi_trader.orchestrator.loops.decision_queue import DECISION_QUEUE_KEY
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from tests.spine.execution.fake_redis import FakeRedis

SYMBOL = "BTCUSDT"
NOW_MS = 4_000_000_000_000


class Rig:
    """Real loop, engine, state and paper exchange over an in-memory Redis."""

    def __init__(self) -> None:
        self.redis = FakeRedis()
        self.price = Decimal(100)
        self.events = AsyncMock()
        self.close_recorder = AsyncMock()
        with patch("kavzi_trader.api.binance.client.BinanceAPIClient"):
            self.exchange = PaperExchangeClient(
                initial_balance_usdt=Decimal(1000),
                commission_rate=Decimal(0),
            )
        self.exchange.get_ticker = AsyncMock(side_effect=self._ticker)  # type: ignore[method-assign]
        self.state = StateManager(RedisConfigSchema(), self.exchange)
        self.state._redis_client._client = self.redis  # type: ignore[assignment]
        self.exchange.set_account_store(self.state.account)
        self.engine = ExecutionEngine(
            exchange=self.exchange,
            state_manager=self.state,
            risk_validator=DynamicRiskValidator(RiskConfigSchema()),
            staleness_checker=StalenessChecker(ExecutionConfigSchema()),
            translator=DecisionTranslator(),
            monitor=OrderMonitor(self.exchange, 1),
            event_store=self.events,
            leverage=1,
            close_recorder=self.close_recorder,
        )
        self.loop = ExecutionLoop(
            redis_client=self.state._redis_client,
            engine=self.engine,
            state_manager=self.state,
        )

    async def _ticker(self, symbol: str) -> TickerSchema:
        return TickerSchema(symbol=symbol, last_price=self.price)

    async def deliver(self, raw: str) -> None:
        self.redis.lists.setdefault(DECISION_QUEUE_KEY, []).append(raw)
        await self.loop._recover_in_flight()
        popped = await self.redis.blmove(
            DECISION_QUEUE_KEY, "kt:decisions:processing", 1
        )
        assert popped is not None
        await self.loop._handle_payload(popped)

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
        created_at_ms=1,
        expires_at_ms=expires_at_ms or NOW_MS,
    )
