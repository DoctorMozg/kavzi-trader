from decimal import Decimal

import pytest

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema, KeyLevelsSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.events.store import RedisEventStore

# NOTE: VolatilityRegime is still imported for fixture construction but the
# volatility gate itself now lives inside ScoutFilter, not in the router.

_ANALYST_REASONING = (
    "EMA alignment is bullish with EMA20 above EMA50 above EMA200. RSI at 55 supports"
    " continuation. Volume confirms the breakout. Volatility regime is NORMAL."
)
_TRADER_REASONING = (
    "Mixed signals across all timeframes. EMA alignment is neutral and RSI is flat"
    " at 50. No clear directional bias to justify a trade entry at this time."
)


class DummyScout:
    def __init__(self, verdict: str) -> None:
        self._verdict = verdict

    async def run(self, deps):
        return ScoutDecisionSchema(
            verdict=self._verdict,
            reason="Test",
            pattern_detected=None,
        )


class DummyAnalyst:
    def __init__(self, setup_valid: bool) -> None:
        self._setup_valid = setup_valid

    async def run(self, deps):
        return AnalystDecisionSchema(
            setup_valid=self._setup_valid,
            direction="NEUTRAL",
            confluence_score=5,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        )


class DummyTrader:
    async def run(self, deps, analyst_result=None):
        return TradeDecisionSchema(
            action="WAIT",
            confidence=0.5,
            reasoning=_TRADER_REASONING,
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
        )


class FakeDepsProvider:
    def __init__(
        self,
        scout_deps: ScoutDependenciesSchema,
        analyst_deps: AnalystDependenciesSchema,
        trader_deps: TradingDependenciesSchema,
    ) -> None:
        self._scout_deps = scout_deps
        self._analyst_deps = analyst_deps
        self._trader_deps = trader_deps
        self.scout_calls = 0
        self.analyst_calls = 0
        self.trader_calls = 0

    def indicators_available(self, symbol: str) -> bool:
        return True

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema:
        self.scout_calls += 1
        return self._scout_deps

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        self.analyst_calls += 1
        return self._analyst_deps

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema:
        self.trader_calls += 1
        return self._trader_deps

    def clear_cycle_cache(self) -> None:
        pass


def _make_provider(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> FakeDepsProvider:
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
    return FakeDepsProvider(scout_deps, analyst_deps, trader_deps)


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
async def test_router_stops_on_invalid_setup(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(False), DummyTrader())
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
    assert result.scout.verdict == "INTERESTING"
    assert result.analyst is not None
    assert result.trader is None
    assert provider.analyst_calls == 1
    assert provider.trader_calls == 0, (
        "Trader deps should not be built on invalid setup"
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
    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(True), DummyTrader())
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


class SpyScout:
    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        self.call_count += 1
        return ScoutDecisionSchema(
            verdict="INTERESTING",
            reason="Test",
            pattern_detected=None,
        )


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
    router = AgentRouter(spy_scout, DummyAnalyst(True), DummyTrader())
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
