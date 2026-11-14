from decimal import Decimal

import pytest

from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.domain.scout_dependencies import ScoutDependenciesSchema
from tests.brain.agent.router_fakes import (
    DummyAnalyst,
    DummyScout,
    DummyTrader,
    SpyScout,
    _make_provider,
)


@pytest.mark.asyncio
async def test_router_stops_on_scout_skip(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    router = AgentRouter(DummyScout("SKIP"), DummyAnalyst(True), DummyTrader())
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    result = await router.run("BTCUSDT", provider)
    assert result.scout.verdict == "SKIP"
    assert result.analyst is None
    assert result.trader is None
    assert provider.scout_calls == 1
    assert provider.analyst_calls == 0, "Analyst deps should not be built on SKIP"
    assert provider.trader_calls == 0, "Trader deps should not be built on SKIP"


@pytest.mark.asyncio
async def test_scout_always_called(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Router always invokes scout (volatility gate is inside scout now)."""
    spy_scout = SpyScout()
    router = AgentRouter(
        spy_scout,
        DummyAnalyst(setup_valid=True, confluence_score=8),
        DummyTrader(),
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
    await router.run("BTCUSDT", provider)
    assert spy_scout.call_count == 1


@pytest.mark.asyncio
async def test_router_handles_empty_candles_without_indexerror(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Regression for H1: a concrete DependenciesProvider returning Scout
    deps with an empty candles list (built via model_construct to bypass
    min_length validation) must not raise IndexError; the pipeline must
    bail out with a SKIP-style result.
    """
    # model_construct skips validation so we can simulate a misbehaving
    # provider upstream — the router is the last line of defense.
    broken_scout_deps = ScoutDependenciesSchema.model_construct(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[],
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    normal = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    normal._scout_deps = broken_scout_deps  # type: ignore[attr-defined]

    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(True), DummyTrader())

    result = await router.run("BTCUSDT", normal)

    assert result.analyst is None
    assert result.trader is None
