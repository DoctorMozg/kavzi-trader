import logging
from decimal import Decimal
from typing import Literal

import pytest

from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.domain.algorithm_confluence import (
    DualConfluenceSchema,
)
from kavzi_trader.domain.analyst_decision import (
    AnalystDecisionSchema,
    KeyLevelSchema,
    KeyLevelsSchema,
)
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.indicator_schemas import (
    TechnicalIndicatorsSchema,
)
from kavzi_trader.domain.state_schemas import AccountStateSchema, PositionSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.indicators.htf import HtfTrendSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from tests.brain.agent.router_fakes import (
    _ANALYST_REASONING,
    DummyAnalyst,
    DummyScout,
    DummyScoutWithPattern,
    DummyTrader,
    FakeDepsProvider,
    SpyTrader,
    _indicators_with_bollinger,
    _make_provider,
)

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
    """confluence=4 + setup_valid=True must NOT reach the Trader tier."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=4)
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
    assert result.analyst.confluence_score == 4
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


# ---------------------------------------------------------------------------
# FGI elevated-fear confluence override
# ---------------------------------------------------------------------------


class FakeConfluenceOverride:
    """Returns a fixed confluence override value."""

    def __init__(self, override: int | None) -> None:
        self._override = override
        self.last_direction: str | None = None

    def get_confluence_override(self, direction: str) -> int | None:
        self.last_direction = direction
        return self._override


@pytest.mark.asyncio
async def test_router_raises_confluence_gate_during_elevated_fear(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """confluence=7 + override=8 → Trader NOT reached (7 < 8)."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=7)
    router = AgentRouter(
        DummyScout("INTERESTING"),
        analyst,
        DummyTrader(),
        confluence_override=FakeConfluenceOverride(8),
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

    assert result.trader is None
    assert provider.trader_calls == 0


@pytest.mark.asyncio
async def test_router_passes_confluence_gate_at_override_threshold(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """confluence=8 + override=8 → Trader IS reached (8 >= 8)."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=8)
    router = AgentRouter(
        DummyScout("INTERESTING"),
        analyst,
        DummyTrader(),
        confluence_override=FakeConfluenceOverride(8),
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
    assert provider.trader_calls == 1


@pytest.mark.asyncio
async def test_router_no_override_uses_default_gate(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """override=None → default gate (6) applies; confluence=6 passes."""
    analyst = DummyAnalyst(setup_valid=True, confluence_score=6)
    router = AgentRouter(
        DummyScout("INTERESTING"),
        analyst,
        DummyTrader(),
        confluence_override=FakeConfluenceOverride(None),
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
    assert provider.trader_calls == 1


@pytest.mark.asyncio
async def test_router_rejects_breakout_overextended_b(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """%B=1.35 + BREAKOUT → Trader NOT called, WAIT returned."""
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
    result = await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 0, "Trader should NOT be called"
    assert result.trader is not None
    assert result.trader.action == "WAIT"
    assert "overextension" in result.trader.reasoning.lower()
    assert "%%B" not in result.trader.reasoning
    assert "Bollinger %B=" in result.trader.reasoning


@pytest.mark.asyncio
async def test_router_allows_breakout_normal_b(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """%B=0.95 + BREAKOUT → Trader IS called."""
    bb_indicators = _indicators_with_bollinger(indicators, Decimal("0.95"))
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
    await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 1


@pytest.mark.asyncio
async def test_router_allows_non_breakout_high_b(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """%B=1.35 + TREND_CONTINUATION → Trader IS called (gate is BREAKOUT-only)."""
    bb_indicators = _indicators_with_bollinger(indicators, Decimal("1.35"))
    spy_trader = SpyTrader()
    router = AgentRouter(
        DummyScoutWithPattern("TREND_CONTINUATION"),
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
    await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 1


@pytest.mark.asyncio
async def test_router_allows_breakout_borderline_b(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """%B=1.15 + BREAKOUT → Trader IS called (caution zone, not reject)."""
    bb_indicators = _indicators_with_bollinger(indicators, Decimal("1.15"))
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
    await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 1


# ---------------------------------------------------------------------------
# Directional breakout %B gate (static method tests)
# ---------------------------------------------------------------------------


def _make_trader_deps_with_bb(
    candle: CandlestickSchema,
    indicators: TechnicalIndicatorsSchema,
    percent_b: Decimal,
    volatility_regime: VolatilityRegime,
    order_flow: OrderFlowSchema,
    algorithm_confluence: DualConfluenceSchema,
    account_state: AccountStateSchema,
    positions: list[PositionSchema],
) -> TradingDependenciesSchema:
    """Build a TradingDependenciesSchema with a specific %B for static tests."""
    bb_indicators = _indicators_with_bollinger(indicators, percent_b)
    return TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=bb_indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
        account_state=account_state,
        open_positions=positions,
    )


def test_pre_trader_breakout_rejects_long_overextended(
    candle: CandlestickSchema,
    indicators: TechnicalIndicatorsSchema,
    volatility_regime: VolatilityRegime,
    order_flow: OrderFlowSchema,
    algorithm_confluence: DualConfluenceSchema,
    account_state: AccountStateSchema,
    positions: list[PositionSchema],
) -> None:
    """%B=1.25, direction=LONG → WAIT (upper overextension)."""
    deps = _make_trader_deps_with_bb(
        candle,
        indicators,
        Decimal("1.25"),
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(True), DummyTrader())
    result = router._trader_pipeline._gates.pre_trader_breakout_check(
        "BTCUSDT",
        "BREAKOUT",
        deps,
        analyst_direction="LONG",
    )
    assert result is not None
    assert result.action == "WAIT"
    assert "upper band" in result.reasoning.lower()


def test_pre_trader_breakout_allows_short_at_high_b(
    candle: CandlestickSchema,
    indicators: TechnicalIndicatorsSchema,
    volatility_regime: VolatilityRegime,
    order_flow: OrderFlowSchema,
    algorithm_confluence: DualConfluenceSchema,
    account_state: AccountStateSchema,
    positions: list[PositionSchema],
) -> None:
    """%B=1.25, direction=SHORT → None (high %B is fine for shorts)."""
    deps = _make_trader_deps_with_bb(
        candle,
        indicators,
        Decimal("1.25"),
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(True), DummyTrader())
    result = router._trader_pipeline._gates.pre_trader_breakout_check(
        "BTCUSDT",
        "BREAKOUT",
        deps,
        analyst_direction="SHORT",
    )
    assert result is None


def test_pre_trader_breakout_rejects_short_overextended(
    candle: CandlestickSchema,
    indicators: TechnicalIndicatorsSchema,
    volatility_regime: VolatilityRegime,
    order_flow: OrderFlowSchema,
    algorithm_confluence: DualConfluenceSchema,
    account_state: AccountStateSchema,
    positions: list[PositionSchema],
) -> None:
    """%B=-0.25, direction=SHORT → WAIT (lower overextension)."""
    deps = _make_trader_deps_with_bb(
        candle,
        indicators,
        Decimal("-0.25"),
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(True), DummyTrader())
    result = router._trader_pipeline._gates.pre_trader_breakout_check(
        "BTCUSDT",
        "BREAKOUT",
        deps,
        analyst_direction="SHORT",
    )
    assert result is not None
    assert result.action == "WAIT"
    assert "lower band" in result.reasoning.lower()


def test_pre_trader_breakout_allows_long_at_low_b(
    candle: CandlestickSchema,
    indicators: TechnicalIndicatorsSchema,
    volatility_regime: VolatilityRegime,
    order_flow: OrderFlowSchema,
    algorithm_confluence: DualConfluenceSchema,
    account_state: AccountStateSchema,
    positions: list[PositionSchema],
) -> None:
    """%B=-0.25, direction=LONG → None (low %B is fine for longs)."""
    deps = _make_trader_deps_with_bb(
        candle,
        indicators,
        Decimal("-0.25"),
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(True), DummyTrader())
    result = router._trader_pipeline._gates.pre_trader_breakout_check(
        "BTCUSDT",
        "BREAKOUT",
        deps,
        analyst_direction="LONG",
    )
    assert result is None


def test_pre_trader_breakout_caution_long_zone(
    candle: CandlestickSchema,
    indicators: TechnicalIndicatorsSchema,
    volatility_regime: VolatilityRegime,
    order_flow: OrderFlowSchema,
    algorithm_confluence: DualConfluenceSchema,
    account_state: AccountStateSchema,
    positions: list[PositionSchema],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """%B=1.15, direction=LONG → None but logs caution warning."""
    deps = _make_trader_deps_with_bb(
        candle,
        indicators,
        Decimal("1.15"),
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(True), DummyTrader())
    with caplog.at_level(logging.WARNING):
        result = router._trader_pipeline._gates.pre_trader_breakout_check(
            "BTCUSDT",
            "BREAKOUT",
            deps,
            analyst_direction="LONG",
        )
    assert result is None
    assert any("caution" in r.message.lower() for r in caplog.records)


def test_pre_trader_breakout_caution_short_zone(
    candle: CandlestickSchema,
    indicators: TechnicalIndicatorsSchema,
    volatility_regime: VolatilityRegime,
    order_flow: OrderFlowSchema,
    algorithm_confluence: DualConfluenceSchema,
    account_state: AccountStateSchema,
    positions: list[PositionSchema],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """%B=-0.15, direction=SHORT → None but logs caution warning."""
    deps = _make_trader_deps_with_bb(
        candle,
        indicators,
        Decimal("-0.15"),
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    router = AgentRouter(DummyScout("INTERESTING"), DummyAnalyst(True), DummyTrader())
    with caplog.at_level(logging.WARNING):
        result = router._trader_pipeline._gates.pre_trader_breakout_check(
            "BTCUSDT",
            "BREAKOUT",
            deps,
            analyst_direction="SHORT",
        )
    assert result is None
    assert any("caution" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Pre-Trader viability gate: the router skips the Trader LLM when no legal
# geometry can reach min R:R. The geometry math itself is covered by
# tests/spine/execution/test_geometry.py; here we assert the router wires
# the gate correctly (proceeds when viable, blocks when not).
# ---------------------------------------------------------------------------


class DummyAnalystWithLevels:
    """Analyst that returns a result with specific key levels and direction."""

    def __init__(
        self,
        direction: Literal["LONG", "SHORT", "NEUTRAL"],
        levels: list[KeyLevelSchema],
        confluence_score: int = 8,
    ) -> None:
        self._direction = direction
        self._levels = levels
        self._confluence_score = confluence_score

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        return AnalystDecisionSchema(
            setup_valid=True,
            direction=self._direction,
            confluence_score=self._confluence_score,
            key_levels=KeyLevelsSchema(levels=self._levels),
            reasoning=_ANALYST_REASONING,
        )


@pytest.mark.asyncio
async def test_router_warns_but_proceeds_on_low_rr(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """When estimated R/R < 1.2, Trader IS still called (soft warning)."""
    # Support=104, resistance=106 at price=105 → Risk=1, Reward=1, R/R=1.0
    levels = [
        KeyLevelSchema(price=Decimal(104), level_type="SUPPORT", reason="test"),
        KeyLevelSchema(price=Decimal(106), level_type="RESISTANCE", reason="test"),
    ]
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("LONG", levels)
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


@pytest.mark.asyncio
async def test_router_passes_trader_on_adequate_rr(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """When estimated R/R >= 1.2, Trader IS called."""
    # Support=100, resistance=120 at price=105 → Risk=5, Reward=15, R/R=3.0
    levels = [
        KeyLevelSchema(price=Decimal(100), level_type="SUPPORT", reason="test"),
        KeyLevelSchema(price=Decimal(120), level_type="RESISTANCE", reason="test"),
    ]
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("LONG", levels)
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


@pytest.mark.asyncio
async def test_router_passes_trader_on_neutral_direction(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Direction=NEUTRAL → R/R check is skipped (fail open)."""
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("NEUTRAL", [], confluence_score=8)
    # NEUTRAL + setup_valid=True + confluence=8 will still reach Trader
    # because the confluence gate passes, and R/R fails open on NEUTRAL
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


# ---------------------------------------------------------------------------
# Viability block: when ATR is so compressed that no legal stop can clear the
# percent floor, no geometry can reach min R:R — skip the Trader LLM call and
# return a WAIT decision straight from the deterministic gate.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_blocks_trader_when_geometry_not_viable(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Compressed ATR → no viable geometry → Trader NOT called, WAIT returned."""
    # price=105; ATR 0.05 makes the 0.15% percent floor (0.1575) exceed the
    # 3x ATR max stop (0.15), so no legal stop exists → not viable.
    compressed = indicators.model_copy(update={"atr_14": Decimal("0.05")})
    levels = [
        KeyLevelSchema(price=Decimal(100), level_type="SUPPORT", reason="test"),
        KeyLevelSchema(price=Decimal(120), level_type="RESISTANCE", reason="test"),
    ]
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("LONG", levels)
    router = AgentRouter(DummyScout("INTERESTING"), analyst, spy_trader)
    provider = _make_provider(
        candle,
        compressed,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    result = await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 0, "Trader must be bypassed when not viable"
    assert result.trader is not None
    assert result.trader.action == "WAIT"
    assert result.trader.confidence == 0.0
    assert "viability block" in result.trader.reasoning.lower()
    assert len(result.trader.reasoning) >= 40


@pytest.mark.asyncio
async def test_router_allows_trader_on_moderate_rr(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """0.5 ≤ R/R < 1.2 → Trader IS called (existing soft-warning path)."""
    # price=105, SUPPORT=100 (risk=5), RESISTANCE=109 (reward=4) → R/R=0.8
    levels = [
        KeyLevelSchema(price=Decimal(100), level_type="SUPPORT", reason="test"),
        KeyLevelSchema(price=Decimal(109), level_type="RESISTANCE", reason="test"),
    ]
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("LONG", levels)
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


@pytest.mark.asyncio
async def test_router_caches_viability_block_wait(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """Second call on the same bar must hit the dedup cache, not re-gate."""
    compressed = indicators.model_copy(update={"atr_14": Decimal("0.05")})
    levels = [
        KeyLevelSchema(price=Decimal(100), level_type="SUPPORT", reason="test"),
        KeyLevelSchema(price=Decimal(120), level_type="RESISTANCE", reason="test"),
    ]
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("LONG", levels)
    router = AgentRouter(DummyScout("INTERESTING"), analyst, spy_trader)
    provider = _make_provider(
        candle,
        compressed,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    first = await router.run("BTCUSDT", provider)
    second = await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 0
    assert first.trader is not None
    assert second.trader is not None
    assert first.trader.action == "WAIT"
    assert second.trader.action == "WAIT"
    # Dedup path returns the same cached instance.
    assert first.trader.reasoning == second.trader.reasoning


@pytest.mark.asyncio
async def test_router_viability_gate_ignores_neutral(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """NEUTRAL direction fails open past the viability gate to the Trader."""
    compressed = indicators.model_copy(update={"atr_14": Decimal("0.05")})
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("NEUTRAL", [], confluence_score=8)
    router = AgentRouter(DummyScout("INTERESTING"), analyst, spy_trader)
    provider = _make_provider(
        candle,
        compressed,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    await router.run("BTCUSDT", provider)

    # Viability is direction-specific; NEUTRAL is not gated and reaches Trader.
    assert spy_trader.call_count == 1


# ---------------------------------------------------------------------------
# HTF soft gate: a setup opposing the 1h trend must clear a bar one point
# higher; an aligned setup passes at the regime gate.
# ---------------------------------------------------------------------------


def _with_htf(
    provider: FakeDepsProvider,
    direction: str,
) -> FakeDepsProvider:
    htf = HtfTrendSchema(
        direction=direction,  # type: ignore[arg-type]
        ema_20=None,
        ema_50=None,
        rsi_14=None,
        bars_1h=60,
    )
    provider._analyst_deps = provider._analyst_deps.model_copy(
        update={"htf_trend": htf}
    )
    return provider


@pytest.mark.asyncio
async def test_counter_htf_setup_blocked_at_regime_gate(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """LONG at exactly the NORMAL gate (6) is blocked when 1h trend is SHORT."""
    levels = [
        KeyLevelSchema(price=Decimal(100), level_type="SUPPORT", reason="test"),
        KeyLevelSchema(price=Decimal(120), level_type="RESISTANCE", reason="test"),
    ]
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("LONG", levels, confluence_score=6)
    router = AgentRouter(DummyScout("INTERESTING"), analyst, spy_trader)
    provider = _with_htf(
        _make_provider(
            candle,
            indicators,
            volatility_regime,
            order_flow,
            algorithm_confluence,
            account_state,
            positions,
        ),
        "SHORT",
    )

    result = await router.run("BTCUSDT", provider)

    # Gate raised 6 -> 7 by the counter-trend rule; score 6 falls short.
    assert spy_trader.call_count == 0
    assert result.trader is None


@pytest.mark.asyncio
async def test_aligned_htf_setup_passes_regime_gate(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    """The same score-6 LONG reaches the Trader when the 1h trend is LONG."""
    levels = [
        KeyLevelSchema(price=Decimal(100), level_type="SUPPORT", reason="test"),
        KeyLevelSchema(price=Decimal(120), level_type="RESISTANCE", reason="test"),
    ]
    spy_trader = SpyTrader()
    analyst = DummyAnalystWithLevels("LONG", levels, confluence_score=6)
    router = AgentRouter(DummyScout("INTERESTING"), analyst, spy_trader)
    provider = _with_htf(
        _make_provider(
            candle,
            indicators,
            volatility_regime,
            order_flow,
            algorithm_confluence,
            account_state,
            positions,
        ),
        "LONG",
    )

    result = await router.run("BTCUSDT", provider)

    assert spy_trader.call_count == 1
    assert result.analyst is not None
