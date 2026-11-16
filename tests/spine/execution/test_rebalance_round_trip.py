from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from kavzi_trader.api.common.models import TickerSchema
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.order_enums import OrderType
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.state_schemas import (
    PositionManagementConfigSchema,
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


def _intent(
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


@pytest.fixture
async def rig() -> Rig:
    rig = Rig()
    await rig.state.reset_for_paper(Decimal(1000))
    return rig


async def test_open_grow_shrink_close_round_trip(rig: Rig) -> None:
    # open: weight 0.3 of 1000 at 100 -> 3 units
    await rig.deliver(_intent("i1", "0.3").model_dump_json())
    pos = await rig.position()
    assert pos is not None
    assert (pos.quantity, pos.entry_price) == (Decimal(3), Decimal(100))
    assert (pos.strategy, pos.exit_policy, pos.take_profit) == ("trend", "SIGNAL", None)
    assert pos.stop_loss == Decimal(70)
    assert await rig.stop_orders() == [(Decimal(3), Decimal(70))]
    position_id = pos.id

    # grow at 110; unrealised pnl is not in paper account state, so equity stays 1000
    rig.price = Decimal(110)
    await rig.deliver(_intent("i2", "0.5").model_dump_json())
    pos = await rig.position()
    assert pos is not None
    grown_qty = Decimal("0.5") * Decimal(1000) / Decimal(110)
    grown_qty = grown_qty.quantize(Decimal("0.00000001"), rounding="ROUND_DOWN")
    assert pos.id == position_id
    assert pos.quantity == grown_qty
    assert pos.entry_price == (
        (Decimal(100) * 3 + Decimal(110) * (grown_qty - 3)) / grown_qty
    )
    assert await rig.stop_orders() == [(grown_qty, pos.stop_loss)]

    # shrink at 110 to 0.1 weight
    await rig.deliver(_intent("i3", "0.1").model_dump_json())
    shrunk = await rig.position()
    assert shrunk is not None
    shrunk_qty = (Decimal("0.1") * Decimal(1000) / Decimal(110)).quantize(
        Decimal("0.00000001"), rounding="ROUND_DOWN"
    )
    assert shrunk.id == position_id
    assert shrunk.quantity == shrunk_qty
    assert shrunk.entry_price == pos.entry_price
    assert await rig.stop_orders() == [(shrunk_qty, shrunk.stop_loss)]

    # close
    rig.price = Decimal(120)
    await rig.deliver(_intent("i4", "0").model_dump_json())
    assert await rig.position() is None
    assert await rig.stop_orders() == []
    rig.close_recorder.record_position_close.assert_awaited_once()
    closed, reason, exit_price = (
        rig.close_recorder.record_position_close.await_args.args
    )
    assert (closed.id, reason, exit_price) == (position_id, "Strategy signal", 120)
    assert exit_price > closed.entry_price  # profitable round trip
    assert rig.redis.lists["kt:decisions:processing"] == []


async def test_same_intent_delivered_twice_places_one_order(rig: Rig) -> None:
    raw = _intent("dup", "0.5").model_dump_json()
    with patch.object(
        rig.exchange, "create_order", wraps=rig.exchange.create_order
    ) as create:
        await rig.deliver(raw)
        market_calls = [
            c
            for c in create.call_args_list
            if c.kwargs["order_type"] == OrderType.MARKET
        ]
        assert len(market_calls) == 1
        await rig.deliver(raw)
        await rig.deliver(_intent("other-id", "0.5").model_dump_json())
        market_calls = [
            c
            for c in create.call_args_list
            if c.kwargs["order_type"] == OrderType.MARKET
        ]
    assert len(market_calls) == 1
    pos = await rig.position()
    assert pos is not None
    assert pos.quantity == Decimal(5)


async def test_events_carry_strategy(rig: Rig) -> None:
    await rig.deliver(_intent("ev", "0.5").model_dump_json())
    await rig.deliver(_intent("ev2", "0").model_dump_json())
    recorded = {
        call.args[0].event_type: call.args[0].data
        for call in rig.events.append.await_args_list
    }
    assert recorded["position_opened"]["strategy"] == "trend"
    assert recorded["position_closed"]["strategy"] == "trend"
    assert recorded["order_created"]["strategy"] == "trend"


async def test_bracket_position_in_symbol_is_not_resized(rig: Rig) -> None:
    now = utc_now()
    bracket = PositionSchema(
        id="llm-1",
        symbol=SYMBOL,
        side="LONG",
        quantity=Decimal(1),
        entry_price=Decimal(100),
        stop_loss=Decimal(95),
        take_profit=Decimal(110),
        current_stop_loss=Decimal(95),
        management_config=PositionManagementConfigSchema(),
        opened_at=now,
        updated_at=now,
    )
    await rig.state.update_position(bracket)
    await rig.deliver(_intent("blocked", "0.5").model_dump_json())
    pos = await rig.position()
    assert pos is not None
    assert pos.exit_policy == "BRACKET"
    assert pos.quantity == Decimal(1)
