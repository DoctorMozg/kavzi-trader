import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.brain.agent.router import PipelineResult
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema, KeyLevelsSchema
from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.state_schemas import PositionManagementConfigSchema
from kavzi_trader.orchestrator.loops.decision_publisher import DecisionPublisher
from kavzi_trader.orchestrator.loops.llm_pipeline_plugin import LlmPipelinePlugin
from kavzi_trader.orchestrator.loops.strategy import StrategyLoop
from kavzi_trader.strategies.bracket_intent_schema import BracketIntentSchema
from tests.orchestrator.test_reasoning_loop import (
    _ANALYST_REASONING,
    _LONG_GEOMETRY,
    _TRADER_REASONING,
    DummyDepsProvider,
    _build_deps,
    _full_gates,
    _long_trader_decision,
)

_VOLATILE_KEYS = {"decision_id", "created_at_ms", "expires_at_ms"}


def _golden_payload() -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "action": "LONG",
        "entry_tactic": "IMMEDIATE",
        "entry_price": "105",
        "stop_loss": "95",
        "take_profit": "125",
        "quantity": None,
        "raw_confidence": 0.8,
        "calibrated_confidence": 0.8,
        "volatility_regime": "NORMAL",
        "position_management": json.loads(
            PositionManagementConfigSchema().model_dump_json()
        ),
        "reasoning": _TRADER_REASONING,
        "current_atr": "2",
        "atr_history": [],
        "leverage": 5,
        "symbol_tier": "TIER_2",
        "size_multiplier": "1",
    }


async def _pushed_payloads() -> list[dict[str, object]]:
    deps = _build_deps()
    router = AsyncMock()
    router.run = AsyncMock(
        return_value=PipelineResult(
            gates=_full_gates(6),
            scout=ScoutDecisionSchema(
                verdict="INTERESTING", reason="ok", pattern_detected=None
            ),
            analyst=AnalystDecisionSchema(
                setup_valid=True,
                direction="LONG",
                confluence_score=7,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning=_ANALYST_REASONING,
            ),
            trader=_long_trader_decision(),
            geometry=_LONG_GEOMETRY,
            trader_deps=deps,
        ),
    )
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()
    plugin = LlmPipelinePlugin(
        position_management=PositionManagementConfigSchema(),
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=DummyDepsProvider(deps),
        interval_s=1,
    )
    loop = StrategyLoop(plugin, DecisionPublisher(redis_client))
    task = asyncio.create_task(loop.run())
    for _ in range(20):
        await asyncio.sleep(0)
        if redis_client.client.lpush.call_count > 0:
            break
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return [json.loads(c.args[1]) for c in redis_client.client.lpush.call_args_list]


@pytest.mark.asyncio
async def test_one_cycle_pushes_the_golden_payload() -> None:
    payloads = await _pushed_payloads()

    assert len(payloads) == 1
    stable = {k: v for k, v in payloads[0].items() if k not in _VOLATILE_KEYS}
    # `kind` and `strategy` are the only additions to the pre-plugin payload.
    assert stable == {
        **_golden_payload(),
        "kind": "bracket",
        "strategy": "llm_pipeline",
    }
    assert Decimal(str(payloads[0]["expires_at_ms"])) > Decimal(
        str(payloads[0]["created_at_ms"])
    )


@pytest.mark.asyncio
async def test_payload_without_kind_parses_as_bracket_intent() -> None:
    legacy = (await _pushed_payloads())[0]
    del legacy["kind"], legacy["strategy"]

    intent = BracketIntentSchema.model_validate(legacy)

    assert (intent.kind, intent.strategy) == ("bracket", "llm_pipeline")
    assert intent.symbol == "BTCUSDT"


@pytest.mark.asyncio
async def test_execution_side_parses_new_payload() -> None:
    payload = (await _pushed_payloads())[0]

    decision = DecisionMessageSchema.model_validate(payload)

    assert (decision.symbol, decision.action) == ("BTCUSDT", "LONG")
