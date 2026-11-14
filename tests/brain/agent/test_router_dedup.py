import logging
from decimal import Decimal
from typing import Literal

import pytest
from pydantic_ai.exceptions import ModelTimeoutError

from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.domain.analyst_decision import (
    AnalystDecisionSchema,
    KeyLevelsSchema,
)
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.scout_dependencies import ScoutDependenciesSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema
from tests.brain.agent.router_fakes import (
    _ANALYST_REASONING,
    CountedUnexpectedModelTrader,
    DummyAnalyst,
    DummyScout,
    DummyScoutWithPattern,
    DummyTrader,
    SpyScout,
    SpyTrader,
    _candle_with_close_time,
    _indicators_with_bollinger,
    _make_provider,
    _rebuild_provider_with_candle,
)


@pytest.mark.asyncio
async def test_router_dedups_analyst_within_same_bar(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Repeat run() calls with the same candle.close_time hit the memo once."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=8)
    router = AgentRouter(DummyScout("INTERESTING"), analyst, DummyTrader())
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    first = await router.run("BTCUSDT", provider)
    second = await router.run("BTCUSDT", provider)

    assert analyst.call_count == 1, (
        "Analyst LLM must only be called once for the same bar"
    )
    assert first.analyst is not None
    assert second.analyst is not None
    # Memo returns the same schema object, preserving conf / valid / reasoning.
    assert second.analyst.confluence_score == first.analyst.confluence_score
    assert second.analyst.setup_valid == first.analyst.setup_valid


@pytest.mark.asyncio
async def test_router_reinvokes_analyst_on_new_bar(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """When close_time advances, the Analyst LLM is called again."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=8)
    router = AgentRouter(DummyScout("INTERESTING"), analyst, DummyTrader())
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await router.run("BTCUSDT", provider)
    assert analyst.call_count == 1

    # Simulate a new 5-minute candle closing.
    new_candle = _candle_with_close_time(candle, 300)
    _rebuild_provider_with_candle(provider, new_candle)

    await router.run("BTCUSDT", provider)
    assert analyst.call_count == 2


@pytest.mark.asyncio
async def test_router_dedups_per_symbol_independently(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Dedup state is keyed by symbol — two symbols must not share a memo."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=8)
    router = AgentRouter(DummyScout("INTERESTING"), analyst, DummyTrader())
    provider_btc = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    provider_eth = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await router.run("BTCUSDT", provider_btc)
    await router.run("ETHUSDT", provider_eth)

    assert analyst.call_count == 2, "Each symbol gets its own first call"


# ---------------------------------------------------------------------------
# Scout bar-close dedup: the router must memoize the Scout result per
# (symbol, candle.close_time). Repeat calls within the same bar return the
# cached result without invoking Scout a second time.
# ---------------------------------------------------------------------------


class SpyScoutSkip:
    """Scout that records call count and always returns SKIP."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        self.call_count += 1
        return ScoutDecisionSchema(
            verdict="SKIP",
            reason="Test skip",
            pattern_detected=None,
        )


@pytest.mark.asyncio
async def test_router_dedups_scout_within_same_bar(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Repeat run() calls with the same candle.close_time hit scout once."""
    spy_scout = SpyScout()
    router = AgentRouter(spy_scout, DummyAnalyst(True, 8), DummyTrader())
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await router.run("BTCUSDT", provider)
    await router.run("BTCUSDT", provider)

    assert spy_scout.call_count == 1, "Scout must only be called once for the same bar"


@pytest.mark.asyncio
async def test_router_reinvokes_scout_on_new_bar(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """When close_time advances, Scout is called again."""
    spy_scout = SpyScout()
    router = AgentRouter(spy_scout, DummyAnalyst(True, 8), DummyTrader())
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await router.run("BTCUSDT", provider)
    assert spy_scout.call_count == 1

    new_candle = _candle_with_close_time(candle, 300)
    _rebuild_provider_with_candle(provider, new_candle)

    await router.run("BTCUSDT", provider)
    assert spy_scout.call_count == 2


@pytest.mark.asyncio
async def test_router_dedups_scout_per_symbol_independently(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Dedup state is keyed by symbol — two symbols get separate calls."""
    spy_scout = SpyScout()
    router = AgentRouter(spy_scout, DummyAnalyst(True, 8), DummyTrader())
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await router.run("BTCUSDT", provider)
    await router.run("ETHUSDT", provider)

    assert spy_scout.call_count == 2, "Each symbol gets its own first call"


@pytest.mark.asyncio
async def test_router_scout_dedup_returns_cached_skip(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Cached SKIP verdicts are returned without re-invoking Scout."""
    spy_skip = SpyScoutSkip()
    router = AgentRouter(spy_skip, DummyAnalyst(True, 8), DummyTrader())
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    first = await router.run("BTCUSDT", provider)
    second = await router.run("BTCUSDT", provider)

    assert spy_skip.call_count == 1
    assert first.scout.verdict == "SKIP"
    assert second.scout.verdict == "SKIP"


# ---------------------------------------------------------------------------
# Trader dedup: memoize the final Trader decision per
# (symbol, analyst_result_hash, candle.close_time). Cross-bar invalidation is
# handled by the bar_close component; a different Analyst result busts the
# cache via the hash component.
# ---------------------------------------------------------------------------


class SwitchableAnalyst:
    """Analyst whose result can be swapped between calls."""

    def __init__(self, result: AnalystDecisionSchema) -> None:
        self._result = result
        self.call_count = 0

    def set_result(self, result: AnalystDecisionSchema) -> None:
        self._result = result

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        self.call_count += 1
        return self._result


def _analyst_decision(
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "LONG",
    confluence_score: int = 8,
) -> AnalystDecisionSchema:
    return AnalystDecisionSchema(
        setup_valid=True,
        direction=direction,
        confluence_score=confluence_score,
        key_levels=KeyLevelsSchema(levels=[]),
        reasoning=_ANALYST_REASONING,
    )


@pytest.mark.asyncio
async def test_router_dedups_trader_on_same_analyst_hash(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Identical Analyst result + same bar → Trader LLM called exactly once."""
    spy_trader = SpyTrader()
    analyst = SwitchableAnalyst(_analyst_decision())
    router = AgentRouter(DummyScout("INTERESTING"), analyst, spy_trader)
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    first = await router.run("BTCUSDT", provider)
    second = await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 1, (
        "Trader LLM must only be called once for the same analyst hash + bar"
    )
    assert first.trader is not None
    assert second.trader is not None
    # Cached result is the same instance as the first decision.
    assert second.trader is first.trader


@pytest.mark.asyncio
async def test_router_reinvokes_trader_on_new_analyst_result(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """When Analyst result changes (e.g. confluence_score), Trader reruns."""
    spy_trader = SpyTrader()
    analyst = SwitchableAnalyst(_analyst_decision(confluence_score=8))
    router = AgentRouter(DummyScout("INTERESTING"), analyst, spy_trader)
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await router.run("BTCUSDT", provider)
    assert spy_trader.call_count == 1

    # Swap in a different analyst result; also clear the Analyst memo so the
    # new result actually reaches _run_trader.
    analyst.set_result(_analyst_decision(confluence_score=9))
    router._dedup.analyst_entries.clear()

    await router.run("BTCUSDT", provider)
    assert spy_trader.call_count == 2, (
        "Hash change must invalidate the Trader dedup cache"
    )


@pytest.mark.asyncio
async def test_router_reinvokes_trader_on_new_bar(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Same Analyst result but a new bar close_time → Trader reruns."""
    spy_trader = SpyTrader()
    analyst = SwitchableAnalyst(_analyst_decision())
    router = AgentRouter(DummyScout("INTERESTING"), analyst, spy_trader)
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await router.run("BTCUSDT", provider)
    assert spy_trader.call_count == 1

    new_candle = _candle_with_close_time(candle, 300)
    _rebuild_provider_with_candle(provider, new_candle)

    await router.run("BTCUSDT", provider)
    assert spy_trader.call_count == 2, (
        "New bar close_time must invalidate the Trader dedup cache"
    )


@pytest.mark.asyncio
async def test_router_does_not_cache_unexpected_model_wait(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """M1: UnexpectedModelBehavior WAIT fallback must NOT be cached so the
    circuit breaker can count consecutive failures and eventually open. A
    cached WAIT would hide retries from the failure counter."""
    trader = CountedUnexpectedModelTrader(bodies=["garbage-1", "garbage-2"])
    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        trader,
    )
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    first = await router.run("BTCUSDT", provider)
    second = await router.run("BTCUSDT", provider)

    assert trader.call_count == 2, (
        "WAIT fallback from UnexpectedModelBehavior must NOT be cached"
    )
    assert first.trader is not None
    assert first.trader.action == "WAIT"
    assert second.trader is not None
    assert second.trader.action == "WAIT"
    assert "BTCUSDT" not in router._dedup.trader_entries


class ExplodingTrader:
    """Raises a generic Exception (NOT UnexpectedModelBehavior)."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
        scout_pattern: str | None = None,
    ) -> TradeDecisionSchema:
        self.call_count += 1
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_router_does_not_cache_on_unhandled_exception(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Generic Exception → empty result, cache untouched, next call retries."""
    trader = ExplodingTrader()
    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        trader,
    )
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    first = await router.run("BTCUSDT", provider)
    second = await router.run("BTCUSDT", provider)

    assert trader.call_count == 2, (
        "Unhandled exception must not poison the Trader dedup cache"
    )
    assert first.trader is None
    assert second.trader is None
    assert "BTCUSDT" not in router._dedup.trader_entries


@pytest.mark.asyncio
async def test_router_caches_breakout_reject_gate(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """breakout_reject WAIT is cached; second call hits dedup without rerun."""
    bb_indicators = _indicators_with_bollinger(indicators, Decimal("1.35"))
    spy_trader = SpyTrader()
    router = AgentRouter(
        DummyScoutWithPattern("BREAKOUT"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        spy_trader,
    )
    provider = _make_provider(
        candle,
        bb_indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    first = await router.run("BTCUSDT", provider)

    with caplog.at_level(logging.INFO):
        second = await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 0, "Trader LLM must not be called either time"
    assert first.trader is not None
    assert first.trader.action == "WAIT"
    assert second.trader is not None
    assert second.trader is first.trader, (
        "Second call must return the cached gate WAIT decision"
    )
    assert any("Trader dedup hit" in r.message for r in caplog.records), (
        "Second call should log a Trader dedup hit"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timeout_exc",
    [
        TimeoutError("Trader timed out"),
        ModelTimeoutError("trader-model", "read timed out", phase="read"),
    ],
    ids=["builtin", "pydantic_ai_transport"],
)
async def test_router_does_not_cache_timeout_wait(
    timeout_exc: Exception,
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """M1: TimeoutError WAIT fallback must NOT be cached — a transient slow
    response should allow retry on the next cycle instead of poisoning the
    dedup cache for the whole bar."""
    call_count = 0

    class CountingTimeoutTrader:
        """Raises TimeoutError and counts invocations."""

        async def run(
            self,
            deps: TradingDependenciesSchema,
            analyst_result: AnalystDecisionSchema | None = None,
            scout_pattern: str | None = None,
        ) -> TradeDecisionSchema:
            nonlocal call_count
            call_count += 1
            raise timeout_exc

    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        CountingTimeoutTrader(),
    )
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    first = await router.run("BTCUSDT", provider)
    second = await router.run("BTCUSDT", provider)

    assert call_count == 2, (
        "TimeoutError WAIT fallback must NOT be cached; next cycle must retry"
    )
    assert first.trader is not None
    assert first.trader.action == "WAIT"
    assert second.trader is not None
    assert second.trader.action == "WAIT"
    assert "BTCUSDT" not in router._dedup.trader_entries
