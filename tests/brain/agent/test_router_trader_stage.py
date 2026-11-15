import logging

import pytest

from kavzi_trader.brain.agent.router import AgentRouter
from tests.brain.agent.router_fakes import (
    CountedUnexpectedModelTrader,
    DummyAnalyst,
    DummyScout,
    DummyTrader,
    _candle_with_close_time,
    _make_provider,
    _rebuild_provider_with_candle,
)


@pytest.mark.asyncio
async def test_router_runs_trader_on_valid_setup(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    router = AgentRouter(
        DummyScout("INTERESTING"),
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
    result = await router.run("BTCUSDT", provider)
    assert result.trader is not None
    assert result.trader_deps is not None
    assert provider.scout_calls == 1
    assert provider.analyst_calls == 1
    assert provider.trader_calls == 1


class TimeoutTrader:
    """Simulates a Trader that hits a timeout."""

    async def run(self, deps, analyst_result=None, scout_pattern=None):
        raise TimeoutError("Trader timed out")


@pytest.mark.asyncio
async def test_router_returns_wait_on_trader_timeout(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        TimeoutTrader(),
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
    result = await router.run("BTCUSDT", provider)
    assert result.trader is not None
    assert result.trader.action == "WAIT"
    assert result.trader.confidence == 0.0
    assert "timed out" in result.trader.reasoning.lower()
    assert result.trader_deps is not None


# ---------------------------------------------------------------------------
# UnexpectedModelBehavior: Trader returns unparseable output
# ---------------------------------------------------------------------------


class UnexpectedModelTrader:
    """Simulates a Trader that returns malformed output."""

    async def run(self, deps, analyst_result=None, scout_pattern=None):
        from pydantic_ai.exceptions import UnexpectedModelBehavior

        raise UnexpectedModelBehavior("Bad output", body="raw json garbage")


@pytest.mark.asyncio
async def test_router_returns_wait_on_unexpected_model_behavior(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        UnexpectedModelTrader(),
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
    result = await router.run("BTCUSDT", provider)

    assert result.trader is not None
    assert result.trader.action == "WAIT"
    assert result.trader.confidence == 0.0
    assert "unparseable" in result.trader.reasoning.lower()
    assert result.trader_deps is not None


@pytest.mark.asyncio
async def test_router_logs_raw_body_on_unexpected_model(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
    caplog: pytest.LogCaptureFixture,
) -> None:
    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        UnexpectedModelTrader(),
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
    with caplog.at_level(logging.WARNING):
        await router.run("BTCUSDT", provider)

    matching = [r for r in caplog.records if "LLM unparseable output" in r.message]
    assert len(matching) >= 1
    record = matching[0]
    assert record.raw_body == "raw json garbage"
    assert record.symbol == "BTCUSDT"


@pytest.mark.asyncio
async def test_router_counts_trader_validation_failures(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
    caplog: pytest.LogCaptureFixture,
) -> None:
    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        CountedUnexpectedModelTrader(bodies=[None, "garbage-1", "garbage-2"]),
    )

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            provider = _make_provider(
                candle,
                indicators,
                volatility_regime,
                order_flow,
                algorithm_confluence,
                account_state,
                positions,
            )
            # Reset per-symbol bar-close dedup state so each pass reaches the
            # Trader tier regardless of cached Scout/Analyst/Trader verdicts.
            router._dedup.scout_entries.clear()
            router._dedup.analyst_entries.clear()
            router._dedup.trader_entries.clear()
            await router.run("BTCUSDT", provider)

    assert router._circuit_breaker.failures["BTCUSDT"] == 3

    matching = [
        r for r in caplog.records if "Trader validation retries exhausted" in r.message
    ]
    assert len(matching) == 3
    counts = [r.trader_validation_failures_total for r in matching]
    assert counts == [1, 2, 3]
    assert all(r.agent == "trader" for r in matching)


@pytest.mark.asyncio
async def test_router_trader_validation_failures_are_per_symbol(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Counter is keyed per-symbol — BTCUSDT failures don't bleed into ETHUSDT."""
    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=True, confluence_score=8),
        CountedUnexpectedModelTrader(bodies=["g1", "g2", "g3"]),
    )

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

    # First BTC call; then advance the bar so the Trader dedup cache does
    # not swallow the second attempt (dedup is keyed on bar_close).
    await router.run("BTCUSDT", provider_btc)
    _rebuild_provider_with_candle(provider_btc, _candle_with_close_time(candle, 900))
    await router.run("BTCUSDT", provider_btc)
    await router.run("ETHUSDT", provider_eth)

    assert router._circuit_breaker.failures["BTCUSDT"] == 2
    assert router._circuit_breaker.failures["ETHUSDT"] == 1


@pytest.mark.asyncio
async def test_router_successful_trader_does_not_increment_counter(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Valid Trader output (even WAIT) must not touch the failure counter."""
    router = AgentRouter(
        DummyScout("INTERESTING"),
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

    result = await router.run("BTCUSDT", provider)

    assert result.trader is not None
    assert result.trader.action == "WAIT"
    assert "BTCUSDT" not in router._circuit_breaker.failures
    assert router._circuit_breaker.failures == {}


@pytest.mark.asyncio
async def test_run_trader_stage_runs_the_trader_on_a_gated_analyst_decision(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    router = AgentRouter(
        DummyScout("INTERESTING"),
        DummyAnalyst(setup_valid=False, confluence_score=8),
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
    stopped = await router.run("BTCUSDT", provider)
    assert stopped.trader is None
    assert provider.trader_calls == 0

    forced = await router.run_trader_stage("BTCUSDT", stopped, provider)

    assert forced.trader is not None
    assert forced.analyst is stopped.analyst
    assert forced.gates is stopped.gates
    assert provider.trader_calls == 1


@pytest.mark.asyncio
async def test_run_trader_stage_rejects_a_result_without_an_analyst_decision(
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
    stopped = await router.run("BTCUSDT", provider)

    with pytest.raises(ValueError, match="Analyst decision"):
        await router.run_trader_stage("BTCUSDT", stopped, provider)
