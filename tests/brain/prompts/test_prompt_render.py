from collections.abc import Callable
from decimal import Decimal

import pytest
from pydantic import SecretStr

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.config import BrainConfigSchema
from kavzi_trader.brain.confluence_thresholds import (
    COUNTER_TREND_GATE_BUMP,
    all_regime_gates,
    confluence_enter_min_for_regime,
)
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.context.context_dicts import SystemPromptContextDict
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.commons.trading_constants import MAX_TP_ATR
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.spine.risk.config import RiskConfigSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.symbol_tier import SymbolTier, SymbolTierConfigSchema
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry

_RISK_CONFIG = RiskConfigSchema()


@pytest.fixture
def prompt_loader() -> PromptLoader:
    return PromptLoader()


@pytest.fixture
def system_context(prompt_loader: PromptLoader) -> SystemPromptContextDict:
    tier = SymbolTierConfigSchema(
        risk_per_trade_percent=Decimal("3.0"),
        max_leverage=5,
        max_exposure_percent=Decimal("20.0"),
        min_confidence=Decimal("0.70"),
        crowded_long_zscore=Decimal("2.0"),
        crowded_short_zscore=Decimal("-2.0"),
    )
    registry = SymbolTierRegistry(
        tier_configs=dict.fromkeys(SymbolTier, tier),
        symbol_map={},
    )
    factory = AgentFactory(
        BrainConfigSchema(openrouter_api_key=SecretStr("test-key")),
        prompt_loader,
        risk_config=_RISK_CONFIG,
        tier_registry=registry,
    )
    return factory._system_prompt_context


@pytest.fixture
def make_deps(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> Callable[
    [VolatilityRegime],
    tuple[AnalystDependenciesSchema, TradingDependenciesSchema],
]:
    def _make(
        regime: VolatilityRegime,
    ) -> tuple[AnalystDependenciesSchema, TradingDependenciesSchema]:
        shared = {
            "symbol": "BTCUSDT",
            "current_price": Decimal(105),
            "timeframe": "15m",
            "recent_candles": [candle],
            "indicators": indicators,
            "order_flow": order_flow,
            "algorithm_confluence": algorithm_confluence,
            "volatility_regime": regime,
        }
        analyst = AnalystDependenciesSchema.model_validate(shared)
        trader = TradingDependenciesSchema(
            **shared,
            account_state=account_state,
            open_positions=positions,
            exchange_client=BinanceClient.__new__(BinanceClient),
            event_store=RedisEventStore.__new__(RedisEventStore),
        )
        return analyst, trader

    return _make


def test_analyst_system_prompt_lists_code_regime_gates(
    prompt_loader: PromptLoader,
    system_context: SystemPromptContextDict,
) -> None:
    rendered = prompt_loader.render_system_prompt("analyst", system_context)

    for regime, gate in all_regime_gates().items():
        assert f"- {regime.value}: {gate}\n" in rendered
    assert f"needs {COUNTER_TREND_GATE_BUMP} more point(s)" in rendered


def test_trader_system_prompt_uses_code_geometry_numbers(
    prompt_loader: PromptLoader,
    system_context: SystemPromptContextDict,
) -> None:
    rendered = prompt_loader.render_system_prompt("trader", system_context)

    max_stop = MAX_TP_ATR / _RISK_CONFIG.min_rr_ratio
    assert f"Keep stop ≤ {max_stop}\u00d7 ATR" in rendered
    assert f"caps the target at {MAX_TP_ATR}\u00d7 ATR" in rendered


def test_trader_system_prompt_leaves_sl_distance_to_spine(
    prompt_loader: PromptLoader,
    system_context: SystemPromptContextDict,
) -> None:
    rendered = prompt_loader.render_system_prompt("trader", system_context)

    assert "entry-to-liquidation" not in rendered
    assert "communicated in each request" not in rendered
    assert "CONFLUENCE SCORING" not in rendered


@pytest.mark.parametrize("regime", list(VolatilityRegime))
def test_user_prompts_carry_the_regime_gate_from_code(
    regime: VolatilityRegime,
    prompt_loader: PromptLoader,
    make_deps: Callable[
        [VolatilityRegime],
        tuple[AnalystDependenciesSchema, TradingDependenciesSchema],
    ],
) -> None:
    analyst_deps, trader_deps = make_deps(regime)
    builder = ContextBuilder()
    gate = confluence_enter_min_for_regime(regime)

    analyst_prompt = prompt_loader.render_user_prompt(
        "analyze_setup",
        builder.build_analyst_context(analyst_deps),
    )
    trader_prompt = prompt_loader.render_user_prompt(
        "make_decision",
        builder.build_trader_context(trader_deps),
    )

    assert f"Confluence gate for this regime: {gate} " in analyst_prompt
    assert f"Analyst confluence gate for this regime: {gate}\n" in trader_prompt
