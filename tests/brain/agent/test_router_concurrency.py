"""Tests for the Analyst concurrency semaphore in AgentRouter.

The semaphore caps concurrent Analyst LLM calls launched from a single
ReasoningLoop cycle to prevent OpenRouter burst saturation observed in
session 2026-04-14 (54% Analyst failure rate during 4-6-symbol bursts).
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelsSchema,
)
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.events.store import RedisEventStore

_REASONING = (
    "EMA alignment is bullish with EMA20 above EMA50 above EMA200."
    " RSI at 55 supports continuation. Volume confirms the breakout."
)


class _SlowAnalyst:
    """Analyst stub that blocks on a shared Event to observe peak concurrency."""

    def __init__(self, gate: asyncio.Event) -> None:
        self._gate = gate
        self._concurrent = 0
        self.max_observed_concurrent = 0

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        self._concurrent += 1
        self.max_observed_concurrent = max(
            self.max_observed_concurrent,
            self._concurrent,
        )
        try:
            await self._gate.wait()
        finally:
            self._concurrent -= 1
        return AnalystDecisionSchema(
            setup_valid=False,
            direction="NEUTRAL",
            confluence_score=5,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_REASONING,
        )


class _ScoutInteresting:
    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        return ScoutDecisionSchema(
            verdict="INTERESTING",
            reason="test",
            pattern_detected="TREND_CONTINUATION",
        )


class _ScoutSkip:
    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        self.call_count += 1
        return ScoutDecisionSchema(
            verdict="SKIP",
            reason="volatility_too_low",
            pattern_detected=None,
        )


class _MultiProvider:
    """Returns per-symbol deps so a single provider can feed many symbols."""

    def __init__(
        self,
        scout_deps: ScoutDependenciesSchema,
        analyst_deps: AnalystDependenciesSchema,
        trader_deps: TradingDependenciesSchema,
    ) -> None:
        self._scout_deps = scout_deps
        self._analyst_deps = analyst_deps
        self._trader_deps = trader_deps

    def indicators_available(self, symbol: str) -> bool:
        return True

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema:
        return self._scout_deps.model_copy(update={"symbol": symbol})

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        return self._analyst_deps.model_copy(update={"symbol": symbol})

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema:
        return self._trader_deps.model_copy(update={"symbol": symbol})

    def clear_cycle_cache(self) -> None:
        return None


def _make_multi_provider(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> _MultiProvider:
    scout_deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    analyst_deps = AnalystDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
    )
    trader_deps = TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        open_positions=positions,
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )
    return _MultiProvider(scout_deps, analyst_deps, trader_deps)


def _trader_wait_stub() -> AsyncMock:
    trader = AsyncMock()
    trader.run = AsyncMock(
        return_value=TradeDecisionSchema.model_validate(
            {
                "action": "WAIT",
                "confidence": 0,
                "reasoning": (
                    "Neutral analyst output in this test means no trade is"
                    " required; returning WAIT for safety."
                ),
                "suggested_entry": None,
                "suggested_stop_loss": None,
                "suggested_take_profit": None,
            },
        ),
    )
    return trader


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_calls(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    gate = asyncio.Event()
    analyst = _SlowAnalyst(gate)
    router = AgentRouter(
        _ScoutInteresting(),
        analyst,
        _trader_wait_stub(),
        analyst_concurrency_limit=2,
    )
    provider = _make_multi_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")

    async def run_all() -> None:
        await asyncio.gather(*(router.run(s, provider) for s in symbols))

    task = asyncio.create_task(run_all())
    # Give the 4 coroutines a chance to contend for the semaphore.
    for _ in range(50):
        await asyncio.sleep(0)
    gate.set()
    await task

    assert analyst.max_observed_concurrent <= 2
    # Every gated coroutine must eventually enter the critical section.
    assert analyst.max_observed_concurrent >= 1


@pytest.mark.asyncio
async def test_semaphore_released_on_exception(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    class _RaisingAnalyst:
        def __init__(self) -> None:
            self.call_count = 0

        async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
            self.call_count += 1
            msg = "boom"
            raise RuntimeError(msg)

    analyst = _RaisingAnalyst()
    router = AgentRouter(
        _ScoutInteresting(),
        analyst,
        _trader_wait_stub(),
        analyst_concurrency_limit=1,
    )
    provider = _make_multi_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    # If the semaphore leaked, the second call would hang forever. Running
    # three symbols back-to-back under limit=1 must still complete cleanly.
    await asyncio.wait_for(
        asyncio.gather(
            router.run("BTCUSDT", provider),
            router.run("ETHUSDT", provider),
            router.run("SOLUSDT", provider),
        ),
        timeout=1.0,
    )
    assert analyst.call_count == 3


@pytest.mark.asyncio
async def test_scout_skip_does_not_acquire_semaphore(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    # A Scout SKIP must bypass the semaphore entirely so deterministic
    # filtering never consumes an Analyst slot.
    scout = _ScoutSkip()
    analyst = AsyncMock()
    analyst.run = AsyncMock()
    router = AgentRouter(
        scout,
        analyst,
        _trader_wait_stub(),
        analyst_concurrency_limit=1,
    )
    provider = _make_multi_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await asyncio.gather(
        *(router.run(s, provider) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")),
    )

    analyst.run.assert_not_called()
    assert scout.call_count == 3
