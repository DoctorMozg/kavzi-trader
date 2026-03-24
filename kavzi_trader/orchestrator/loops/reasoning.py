import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol, cast
from uuid import uuid4

from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.spine.execution.decision_message_schema import DecisionMessageSchema
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import PositionManagementConfigSchema

logger = logging.getLogger(__name__)


class DependenciesProvider(Protocol):
    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema: ...

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema: ...

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema: ...


class ReasoningLoop:
    """Runs the agent router and enqueues trade decisions."""

    def __init__(
        self,
        symbols: list[str],
        router: AgentRouter,
        deps_provider: DependenciesProvider,
        redis_client: RedisStateClient,
        queue_key: str = "kt:decisions:pending",
        interval_s: int = 5,
    ) -> None:
        self._symbols = symbols
        self._router = router
        self._deps_provider = deps_provider
        self._redis_client = redis_client
        self._queue_key = queue_key
        self._interval_s = interval_s

    async def run(self) -> None:
        while True:
            try:
                for symbol in self._symbols:
                    await self._handle_symbol(symbol)
            except Exception:
                logger.exception("ReasoningLoop encountered an error, continuing")
            await asyncio.sleep(self._interval_s)

    async def _handle_symbol(self, symbol: str) -> None:
        scout_deps = await self._deps_provider.get_scout(symbol)
        analyst_deps = await self._deps_provider.get_analyst(symbol)
        trader_deps = await self._deps_provider.get_trader(symbol)

        scout, analyst, trader = await self._router.run(
            scout_deps=scout_deps,
            analyst_deps=analyst_deps,
            trader_deps=trader_deps,
        )
        if not self._should_enqueue(scout, analyst, trader):
            return
        if trader is None:
            return
        decision = self._build_decision_message(trader, trader_deps)
        await self._redis_client.client.lpush(
            self._queue_key,
            decision.model_dump_json(),
        )

    def _should_enqueue(
        self,
        scout: ScoutDecisionSchema,
        analyst: AnalystDecisionSchema | None,
        trader: TradeDecisionSchema | None,
    ) -> bool:
        if scout.verdict != "INTERESTING":
            return False
        if analyst is None or not analyst.setup_valid:
            return False
        if trader is None:
            return False
        return trader.action in {"BUY", "SELL", "CLOSE"}

    def _build_decision_message(
        self,
        trader: TradeDecisionSchema,
        deps: TradingDependenciesSchema,
    ) -> DecisionMessageSchema:
        now = datetime.now(UTC)
        decision_id = str(uuid4())
        position_management = PositionManagementConfigSchema()
        if trader.position_management is not None:
            position_management = PositionManagementConfigSchema.model_validate(
                trader.position_management.model_dump(),
            )

        entry_price = trader.suggested_entry or deps.current_price
        stop_loss = trader.suggested_stop_loss or entry_price
        take_profit = trader.suggested_take_profit or entry_price
        atr = deps.indicators.atr_14 or Decimal("0")
        if trader.action not in {"BUY", "SELL", "CLOSE"}:
            raise ValueError("Unsupported action for execution queue")
        action = cast(Literal["BUY", "SELL", "CLOSE"], trader.action)

        return DecisionMessageSchema(
            decision_id=decision_id,
            symbol=deps.symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=Decimal("0"),
            raw_confidence=trader.confidence,
            calibrated_confidence=trader.calibrated_confidence
            if trader.calibrated_confidence is not None
            else trader.confidence,
            volatility_regime=deps.volatility_regime,
            position_management=position_management,
            created_at_ms=int(now.timestamp() * 1000),
            expires_at_ms=int(now.timestamp() * 1000) + 60_000,
            current_atr=atr,
            atr_history=[],
        )
