import pytest

from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
)
from kavzi_trader.domain.algorithm_confluence import (
    AlgorithmConfluenceSchema,
    DualConfluenceSchema,
)
from kavzi_trader.domain.analyst_decision import (
    AnalystDecisionSchema,
    KeyLevelsSchema,
)
from tests.brain.agent.router_fakes import (
    _ANALYST_REASONING,
    DummyAnalyst,
    DummyScout,
    DummyTrader,
    _make_provider,
)


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
    """Both sides score below the default analyst gate threshold (2)."""
    low = AlgorithmConfluenceSchema(
        ema_alignment=True,
        rsi_favorable=False,
        volume_above_average=False,
        price_at_bollinger=False,
        funding_favorable=False,
        oi_supports_direction=False,
        oi_funding_divergence=False,
        volume_spike=False,
        score=1,
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
    # Default fixture has long.score=4, threshold default is 2 → not skipped
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


def _make_both_sides_zero() -> DualConfluenceSchema:
    """Both long and short score 0 — all indicators returned False."""
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
    return DualConfluenceSchema(long=zero, short=zero, detected_side="LONG")


def _make_detected_zero_opposite_strong() -> DualConfluenceSchema:
    """detected_side=LONG scores 0; opposite SHORT scores 5.

    Under the old buggy gate (check detected_side only) this would skip the
    Analyst even though the SHORT side has real signal; the corrected gate
    must NOT skip this case.
    """
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
async def test_router_skips_analyst_when_both_sides_zero(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    account_state,
    positions,
) -> None:
    """When BOTH long and short confluence are 0/8, Analyst LLM is skipped."""
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
        _make_both_sides_zero(),
        account_state,
        positions,
    )
    result = await router.run("BTCUSDT", provider)

    assert spy_analyst.call_count == 0, "Analyst should be skipped"
    assert result.analyst is not None
    assert result.analyst.setup_valid is False
    assert result.analyst.confluence_score == 0
    assert result.analyst.direction == "NEUTRAL"


@pytest.mark.asyncio
async def test_router_calls_analyst_when_opposite_side_has_signal(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    account_state,
    positions,
) -> None:
    """Regression for H2: detected_side=LONG with score 0 but SHORT side has
    signal should NOT skip. The gate must evaluate both sides, not trust the
    static detected_side attribute.
    """
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
        _make_detected_zero_opposite_strong(),
        account_state,
        positions,
    )
    result = await router.run("BTCUSDT", provider)

    assert spy_analyst.call_count == 1, (
        "Analyst must run when any side has signal, even if detected_side"
        " is the zero-score side"
    )
    assert result.analyst is not None


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
