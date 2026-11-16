import asyncio
import json
from collections.abc import Callable
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.execution_result import ExecutionResultSchema
from kavzi_trader.domain.state_schemas import PositionManagementConfigSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.strategies.bracket_intent_schema import BracketIntentSchema
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)


@pytest.mark.asyncio
async def test_execution_loop_dispatches() -> None:
    decision = DecisionMessageSchema(
        decision_id="decision-1",
        symbol="BTCUSDT",
        action="LONG",
        entry_price=Decimal(100),
        stop_loss=Decimal(95),
        take_profit=Decimal(110),
        quantity=Decimal(1),
        raw_confidence=0.8,
        calibrated_confidence=0.7,
        volatility_regime=VolatilityRegime.NORMAL,
        position_management=PositionManagementConfigSchema(),
        created_at_ms=1,
        expires_at_ms=60_000,
        current_atr=Decimal(2),
        atr_history=[],
    )
    redis_client = AsyncMock()
    redis_client.client.blmove = AsyncMock(
        side_effect=[decision.model_dump_json(), None],
    )
    redis_client.client.lmove = AsyncMock(return_value=None)
    redis_client.client.lrem = AsyncMock()
    engine = AsyncMock()

    state_manager = AsyncMock()
    loop = ExecutionLoop(
        redis_client=redis_client,
        engine=engine,
        state_manager=state_manager,
    )
    task = asyncio.create_task(loop.run())
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    engine.execute.assert_called_once()


# ---- ORC-04: a decision must survive a failing engine.execute ----------------


class _FakeRedisLists:
    """Minimal in-memory list commands used by the reliable-queue loop."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    async def lpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).insert(0, value)

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def blmove(
        self,
        first_list: str,
        second_list: str,
        timeout: int,  # noqa: ASYNC109 - mirrors redis-py blmove signature
        src: str = "LEFT",
        dest: str = "RIGHT",
    ) -> str | None:
        source = self.lists.get(first_list, [])
        if not source:
            await asyncio.sleep(0.001)
            return None
        value = source.pop(0 if src == "LEFT" else -1)
        target = self.lists.setdefault(second_list, [])
        target.insert(0, value) if dest == "LEFT" else target.append(value)
        return value

    async def lmove(
        self,
        first_list: str,
        second_list: str,
        src: str = "LEFT",
        dest: str = "RIGHT",
    ) -> str | None:
        source = self.lists.get(first_list, [])
        if not source:
            return None
        value = source.pop(0 if src == "LEFT" else -1)
        target = self.lists.setdefault(second_list, [])
        target.insert(0, value) if dest == "LEFT" else target.append(value)
        return value

    async def lrem(self, key: str, count: int, value: str) -> int:
        items = self.lists.get(key, [])
        if value in items:
            items.remove(value)
            return 1
        return 0


def _decision() -> DecisionMessageSchema:
    return DecisionMessageSchema(
        decision_id="decision-1",
        symbol="BTCUSDT",
        action="LONG",
        entry_price=Decimal(100),
        stop_loss=Decimal(95),
        take_profit=Decimal(110),
        quantity=Decimal(1),
        raw_confidence=0.8,
        calibrated_confidence=0.7,
        volatility_regime=VolatilityRegime.NORMAL,
        position_management=PositionManagementConfigSchema(),
        created_at_ms=1,
        expires_at_ms=60_000,
        current_atr=Decimal(2),
        atr_history=[],
    )


async def _run_loop_until(
    loop: ExecutionLoop,
    condition: Callable[[], bool],
) -> None:
    task = asyncio.create_task(loop.run())
    try:
        async with asyncio.timeout(2):
            while not condition():
                await asyncio.sleep(0.005)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_decision_is_retried_after_engine_failure() -> None:
    fake = _FakeRedisLists()
    await fake.lpush("kt:decisions:pending", _decision().model_dump_json())
    redis_client = MagicMock()
    redis_client.client = fake
    engine = AsyncMock()
    engine.execute = AsyncMock(
        side_effect=[
            RuntimeError("exchange down"),
            ExecutionResultSchema(decision_id="decision-1", status="FILLED"),
        ],
    )
    loop = ExecutionLoop(
        redis_client=redis_client,
        engine=engine,
        state_manager=AsyncMock(),
    )

    await _run_loop_until(loop, lambda: engine.execute.call_count >= 2)
    await asyncio.sleep(0.02)

    assert engine.execute.call_count == 2
    assert fake.lists["kt:decisions:pending"] == []
    assert fake.lists["kt:decisions:processing"] == []
    assert not fake.lists.get("kt:decisions:failed")


@pytest.mark.asyncio
async def test_poison_decision_is_dead_lettered_after_max_attempts() -> None:
    fake = _FakeRedisLists()
    payload = _decision().model_dump_json()
    await fake.lpush("kt:decisions:pending", payload)
    redis_client = MagicMock()
    redis_client.client = fake
    engine = AsyncMock()
    engine.execute = AsyncMock(side_effect=RuntimeError("always broken"))
    loop = ExecutionLoop(
        redis_client=redis_client,
        engine=engine,
        state_manager=AsyncMock(),
    )

    await _run_loop_until(loop, lambda: bool(fake.lists.get("kt:decisions:failed")))
    await asyncio.sleep(0.02)

    assert fake.lists["kt:decisions:failed"] == [payload]
    assert fake.lists["kt:decisions:pending"] == []
    assert fake.lists["kt:decisions:processing"] == []
    assert engine.execute.call_count == 3


@pytest.mark.asyncio
async def test_in_flight_decision_is_recovered_on_startup() -> None:
    fake = _FakeRedisLists()
    await fake.rpush("kt:decisions:processing", _decision().model_dump_json())
    redis_client = MagicMock()
    redis_client.client = fake
    engine = AsyncMock()
    engine.execute = AsyncMock(
        return_value=ExecutionResultSchema(decision_id="decision-1", status="FILLED"),
    )
    loop = ExecutionLoop(
        redis_client=redis_client,
        engine=engine,
        state_manager=AsyncMock(),
    )

    await _run_loop_until(loop, lambda: engine.execute.call_count >= 1)

    engine.execute.assert_called_once()


def _target_weight_payload() -> str:
    return TargetWeightIntentSchema(
        strategy="trend",
        intent_id="tw-1",
        symbol="BTCUSDT",
        target_weight=Decimal("0.1"),
        disaster_stop_pct=Decimal("0.3"),
        created_at_ms=1,
        expires_at_ms=60_000,
    ).model_dump_json()


async def _run_one_payload(payload: str) -> tuple[AsyncMock, _FakeRedisLists]:
    fake = _FakeRedisLists()
    await fake.lpush("kt:decisions:pending", payload)
    redis_client = MagicMock()
    redis_client.client = fake
    engine = AsyncMock()
    loop = ExecutionLoop(
        redis_client=redis_client,
        engine=engine,
        state_manager=AsyncMock(),
    )
    await _run_loop_until(
        loop,
        lambda: bool(
            engine.execute.call_count or engine.rebalance.execute.call_count,
        ),
    )
    await asyncio.sleep(0.02)
    return engine, fake


@pytest.mark.asyncio
async def test_payload_without_kind_routes_to_bracket_path() -> None:
    legacy = json.loads(_decision().model_dump_json())
    assert "kind" not in legacy

    engine, fake = await _run_one_payload(json.dumps(legacy))

    engine.execute.assert_called_once()
    assert isinstance(engine.execute.call_args.args[0], BracketIntentSchema)
    engine.rebalance.execute.assert_not_called()
    assert fake.lists["kt:decisions:processing"] == []


@pytest.mark.asyncio
async def test_target_weight_payload_routes_to_rebalance_executor() -> None:
    engine, fake = await _run_one_payload(_target_weight_payload())

    engine.rebalance.execute.assert_called_once()
    assert engine.rebalance.execute.call_args.args[0].intent_id == "tw-1"
    engine.execute.assert_not_called()
    assert fake.lists["kt:decisions:processing"] == []


@pytest.mark.asyncio
async def test_unknown_kind_is_dead_lettered() -> None:
    payload = json.dumps({**json.loads(_decision().model_dump_json()), "kind": "x"})
    fake = _FakeRedisLists()
    await fake.lpush("kt:decisions:pending", payload)
    redis_client = MagicMock()
    redis_client.client = fake
    loop = ExecutionLoop(
        redis_client=redis_client,
        engine=AsyncMock(),
        state_manager=AsyncMock(),
    )

    await _run_loop_until(loop, lambda: bool(fake.lists.get("kt:decisions:failed")))

    assert fake.lists["kt:decisions:failed"] == [payload]
