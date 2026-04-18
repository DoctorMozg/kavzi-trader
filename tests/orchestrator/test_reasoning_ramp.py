"""Progressive idle-ramp tests for ReasoningLoop.

Verifies the staircase (3 -> 240s, 5 -> 480s, 8 -> 720s) and that an
INTERESTING cycle fully resets the counter back to the base interval.
"""

import asyncio
import unittest.mock
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.brain.agent.router import PipelineResult
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop


@pytest.fixture
def skip_result() -> PipelineResult:
    return PipelineResult(
        scout=ScoutDecisionSchema(
            verdict="SKIP",
            reason="dead market",
            pattern_detected=None,
        ),
    )


@pytest.fixture
def interesting_result() -> PipelineResult:
    return PipelineResult(
        scout=ScoutDecisionSchema(
            verdict="INTERESTING",
            reason="volume",
            pattern_detected=None,
        ),
    )


async def _run_until_sleeps(
    loop: ReasoningLoop,
    sleep_durations: list[float],
    *,
    target_sleep_count: int,
    max_ticks: int = 400,
) -> None:
    original_sleep = asyncio.sleep

    async def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await original_sleep(0)

    with unittest.mock.patch("asyncio.sleep", side_effect=_capture_sleep):
        task = asyncio.create_task(loop.run())
        for _ in range(max_ticks):
            await original_sleep(0)
            if len(sleep_durations) >= target_sleep_count:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def _build_skip_loop(router: AsyncMock) -> ReasoningLoop:
    deps_provider = AsyncMock()
    deps_provider.clear_cycle_cache = unittest.mock.MagicMock()
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()
    return ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=deps_provider,
        redis_client=redis_client,
        interval_s=10,
    )


@pytest.mark.asyncio
async def test_idle_3_cycles_sleeps_240s(skip_result: PipelineResult) -> None:
    router = AsyncMock()
    router.run = AsyncMock(return_value=skip_result)
    loop = _build_skip_loop(router)

    sleeps: list[float] = []
    await _run_until_sleeps(loop, sleeps, target_sleep_count=3)

    assert sleeps[0] == 10.0
    assert sleeps[1] == 10.0
    assert sleeps[2] == 240.0


@pytest.mark.asyncio
async def test_idle_5_cycles_sleeps_480s(skip_result: PipelineResult) -> None:
    router = AsyncMock()
    router.run = AsyncMock(return_value=skip_result)
    loop = _build_skip_loop(router)

    sleeps: list[float] = []
    await _run_until_sleeps(loop, sleeps, target_sleep_count=5)

    # Stairs at idle counts 3, 5, 8 -> 240, 480, 720.
    assert sleeps[2] == 240.0
    assert sleeps[3] == 240.0
    assert sleeps[4] == 480.0


@pytest.mark.asyncio
async def test_idle_8_cycles_sleeps_720s(skip_result: PipelineResult) -> None:
    router = AsyncMock()
    router.run = AsyncMock(return_value=skip_result)
    loop = _build_skip_loop(router)

    sleeps: list[float] = []
    await _run_until_sleeps(loop, sleeps, target_sleep_count=8)

    assert sleeps[4] == 480.0
    assert sleeps[5] == 480.0
    assert sleeps[6] == 480.0
    assert sleeps[7] == 720.0


@pytest.mark.asyncio
async def test_interesting_resets_ramp(
    skip_result: PipelineResult,
    interesting_result: PipelineResult,
) -> None:
    """Once we are already sitting at the 240s stair, a single INTERESTING
    cycle must reset the counter fully so the NEXT idle returns to base.
    """
    call_count = 0

    async def _pattern(symbol: str, deps_provider: object) -> PipelineResult:
        nonlocal call_count
        call_count += 1
        # Cycles 1-3 SKIP (hit the 240s stair on cycle 3), cycle 4 is
        # INTERESTING, cycle 5 SKIP again — must drop to base not 240s.
        if call_count == 4:
            return interesting_result
        return skip_result

    router = AsyncMock()
    router.run = AsyncMock(side_effect=_pattern)
    loop = _build_skip_loop(router)

    sleeps: list[float] = []
    await _run_until_sleeps(loop, sleeps, target_sleep_count=5)

    assert sleeps[0] == 10.0
    assert sleeps[1] == 10.0
    # 3rd idle stair fires.
    assert sleeps[2] == 240.0
    # Interesting cycle resets to base.
    assert sleeps[3] == 10.0
    # First idle after reset is back to base, not 240.
    assert sleeps[4] == 10.0
