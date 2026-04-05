from datetime import timedelta
from decimal import Decimal

import pytest

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
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
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
    DualConfluenceSchema,
)

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
    def __init__(self, setup_valid: bool, confluence_score: int = 5) -> None:
        self._setup_valid = setup_valid
        self._confluence_score = confluence_score
        self.call_count = 0

    async def run(self, deps):
        self.call_count += 1
        return AnalystDecisionSchema(
            setup_valid=self._setup_valid,
            direction="NEUTRAL",
            confluence_score=self._confluence_score,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        )


class DummyTrader:
    async def run(self, deps, analyst_result=None, scout_pattern=None):
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


class SpyAnalyst:
    """Analyst that records whether it was called."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        self.call_count += 1
        return AnalystDecisionSchema(
            setup_valid=True,
            direction="SHORT",
            confluence_score=8,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        )


def _make_low_confluence() -> DualConfluenceSchema:
    """Both sides score below the default analyst gate threshold (3)."""
    low = AlgorithmConfluenceSchema(
        ema_alignment=True,
        rsi_favorable=True,
        volume_above_average=False,
        price_at_bollinger=False,
        funding_favorable=False,
        oi_supports_direction=False,
        oi_funding_divergence=False,
        volume_spike=False,
        score=2,
    )
    return DualConfluenceSchema(long=low, short=low, detected_side="SHORT")


@pytest.mark.asyncio
async def test_router_skips_analyst_on_low_confluence(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    account_state,
    positions,
) -> None:
    """When max algorithm confluence < threshold, Analyst LLM is not called."""
    spy_analyst = SpyAnalyst()
    router = AgentRouter(
        DummyScout("INTERESTING"),
        spy_analyst,
        DummyTrader(),
    )
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        _make_low_confluence(),
        account_state,
        positions,
    )
    result = await router.run("BTCUSDT", provider)

    assert spy_analyst.call_count == 0, "Analyst LLM should not be called"
    assert result.analyst is not None
    assert result.analyst.setup_valid is False
    assert "skipped" in result.analyst.reasoning.lower()
    assert result.trader is None


@pytest.mark.asyncio
async def test_router_calls_analyst_at_threshold(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """When max algo confluence == threshold, Analyst IS called (gate is <)."""
    spy_analyst = SpyAnalyst()
    # Default fixture has long.score=4, threshold default is 3 → not skipped
    router = AgentRouter(
        DummyScout("INTERESTING"),
        spy_analyst,
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

    assert spy_analyst.call_count == 1, "Analyst should be called at threshold"
    assert result.analyst is not None
    assert result.analyst.setup_valid is True


def _make_detected_side_zero() -> DualConfluenceSchema:
    """Detected side (LONG) scores 0; opposite side scores above threshold."""
    zero = AlgorithmConfluenceSchema(
        ema_alignment=False,
        rsi_favorable=False,
        volume_above_average=False,
        price_at_bollinger=False,
        funding_favorable=False,
        oi_supports_direction=False,
        oi_funding_divergence=False,
        volume_spike=False,
        score=0,
    )
    high = AlgorithmConfluenceSchema(
        ema_alignment=True,
        rsi_favorable=True,
        volume_above_average=True,
        price_at_bollinger=True,
        funding_favorable=True,
        oi_supports_direction=False,
        oi_funding_divergence=False,
        volume_spike=False,
        score=5,
    )
    return DualConfluenceSchema(long=zero, short=high, detected_side="LONG")


@pytest.mark.asyncio
async def test_router_skips_analyst_when_detected_side_zero(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    account_state,
    positions,
) -> None:
    """When detected side has confluence 0/8, Analyst LLM is not called."""
    spy_analyst = SpyAnalyst()
    router = AgentRouter(
        DummyScout("INTERESTING"),
        spy_analyst,
        DummyTrader(),
    )
    provider = _make_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        _make_detected_side_zero(),
        account_state,
        positions,
    )
    result = await router.run("BTCUSDT", provider)

    assert spy_analyst.call_count == 0, "Analyst should be skipped"
    assert result.analyst is not None
    assert result.analyst.setup_valid is False
    assert result.analyst.confluence_score == 0
    assert "stale" in result.analyst.reasoning.lower()


@pytest.mark.asyncio
async def test_router_calls_analyst_when_detected_side_nonzero(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """When detected side has score >= 1, gate 2 does not block."""
    spy_analyst = SpyAnalyst()
    router = AgentRouter(
        DummyScout("INTERESTING"),
        spy_analyst,
        DummyTrader(),
    )
    # Default fixture has long.score=4, detected_side="LONG" → nonzero
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

    assert spy_analyst.call_count == 1
    assert result.analyst is not None


# ---------------------------------------------------------------------------
# Bar-close dedup: the router must memoize the Analyst result per
# (symbol, candle.close_time). Repeat calls within the same bar return the
# cached result without invoking the LLM a second time.
# ---------------------------------------------------------------------------


def _candle_with_close_time(
    base: CandlestickSchema, offset_s: int
) -> CandlestickSchema:
    return CandlestickSchema(
        open_time=base.open_time + timedelta(seconds=offset_s),
        close_time=base.close_time + timedelta(seconds=offset_s),
        open_price=base.open_price,
        high_price=base.high_price,
        low_price=base.low_price,
        close_price=base.close_price,
        volume=base.volume,
        quote_volume=base.quote_volume,
        trades_count=base.trades_count,
        taker_buy_base_volume=base.taker_buy_base_volume,
        taker_buy_quote_volume=base.taker_buy_quote_volume,
        interval=base.interval,
        symbol=base.symbol,
    )


def _rebuild_provider_with_candle(
    provider: FakeDepsProvider,
    new_candle: CandlestickSchema,
) -> None:
    """Swap in deps whose recent_candles[-1] is the new candle."""
    provider._scout_deps = provider._scout_deps.model_copy(
        update={"recent_candles": [new_candle]},
    )
    provider._analyst_deps = provider._analyst_deps.model_copy(
        update={"recent_candles": [new_candle]},
    )
    provider._trader_deps = provider._trader_deps.model_copy(
        update={"recent_candles": [new_candle]},
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
# Confluence entry gate: setup_valid alone is not enough — confluence must
# also be >= 7. Scores 5-6 with setup_valid=True short-circuit before Trader.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_blocks_trader_when_confluence_below_entry_gate(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """confluence=5 + setup_valid=True must NOT reach the Trader tier."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=5)
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
    result = await router.run("BTCUSDT", provider)

    assert result.analyst is not None
    assert result.analyst.setup_valid is True
    assert result.analyst.confluence_score == 5
    assert result.trader is None
    assert provider.trader_calls == 0


@pytest.mark.asyncio
async def test_router_enters_trader_at_confluence_entry_gate(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """confluence=6 + setup_valid=True is the minimum to reach Trader."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=6)
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
    result = await router.run("BTCUSDT", provider)

    assert result.trader is not None
    assert provider.trader_calls == 1


@pytest.mark.asyncio
async def test_router_blocks_trader_when_llm_rejects_high_confluence(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """confluence=9 but setup_valid=False must NOT reach Trader (trust the LLM)."""
    analyst = DummyAnalyst(setup_valid=False, confluence_score=9)
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
    result = await router.run("BTCUSDT", provider)

    assert result.analyst is not None
    assert result.analyst.setup_valid is False
    assert result.trader is None
    assert provider.trader_calls == 0
