"""Router regime-gate tests.

After Phase 4 the volatility penalty is applied by the router, not the
LLM. The escalation gate is regime-specific (NORMAL=6, HIGH=7, EXTREME=8,
LOW=7) against the Analyst's raw confluence_score.
"""

from decimal import Decimal

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
from kavzi_trader.spine.risk.schemas import VolatilityRegime

_REASONING = (
    "EMA alignment is bullish with EMA20 above EMA50 above EMA200."
    " RSI at 55 supports continuation. Volume confirms the breakout."
)
_TRADER_REASONING = (
    "Volatility is contained and the setup aligns with the higher-timeframe"
    " trend. Taking entry at current price with ATR-based stop."
)


class _Scout:
    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        return ScoutDecisionSchema(
            verdict="INTERESTING",
            reason="test",
            pattern_detected="TREND_CONTINUATION",
        )


class _Analyst:
    def __init__(self, *, confluence_score: int, setup_valid: bool = True) -> None:
        self._score = confluence_score
        self._valid = setup_valid
        self.call_count = 0

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        self.call_count += 1
        return AnalystDecisionSchema(
            setup_valid=self._valid,
            direction="LONG",
            confluence_score=self._score,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_REASONING,
        )


class _Trader:
    def __init__(self) -> None:
        self.call_count = 0

    async def run(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
        scout_pattern: str | None = None,
    ) -> TradeDecisionSchema:
        self.call_count += 1
        return TradeDecisionSchema(
            action="WAIT",
            confidence=0.1,
            reasoning=_TRADER_REASONING,
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
        )


class _Provider:
    def __init__(
        self,
        candle,
        indicators,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
        regime: VolatilityRegime,
    ) -> None:
        self._scout_deps = ScoutDependenciesSchema(
            symbol="BTCUSDT",
            current_price=Decimal(105),
            timeframe="15m",
            recent_candles=[candle],
            indicators=indicators,
            volatility_regime=regime,
        )
        self._analyst_deps = AnalystDependenciesSchema(
            symbol="BTCUSDT",
            current_price=Decimal(105),
            timeframe="15m",
            recent_candles=[candle],
            indicators=indicators,
            order_flow=order_flow,
            algorithm_confluence=algorithm_confluence,
            volatility_regime=regime,
        )
        self._trader_deps = TradingDependenciesSchema(
            symbol="BTCUSDT",
            current_price=Decimal(105),
            timeframe="15m",
            recent_candles=[candle],
            indicators=indicators,
            order_flow=order_flow,
            algorithm_confluence=algorithm_confluence,
            volatility_regime=regime,
            account_state=account_state,
            open_positions=positions,
            exchange_client=BinanceClient.__new__(BinanceClient),
            event_store=RedisEventStore.__new__(RedisEventStore),
        )

    def indicators_available(self, symbol: str) -> bool:
        return True

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema:
        return self._scout_deps

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        return self._analyst_deps

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema:
        return self._trader_deps

    def clear_cycle_cache(self) -> None:
        return None


@pytest.mark.parametrize(
    ("regime", "score", "expected_trader_calls"),
    [
        # NORMAL-regime gate is 6 (parity with legacy flat constant).
        (VolatilityRegime.NORMAL, 6, 1),
        (VolatilityRegime.NORMAL, 5, 0),
        # HIGH-regime gate is 7 — raw 6 no longer escalates.
        (VolatilityRegime.HIGH, 7, 1),
        (VolatilityRegime.HIGH, 6, 0),
        # EXTREME-regime gate is 8 — genuinely strong setups still trade.
        (VolatilityRegime.EXTREME, 8, 1),
        (VolatilityRegime.EXTREME, 7, 0),
        # LOW-regime gate is 7 (same as HIGH).
        (VolatilityRegime.LOW, 7, 1),
        (VolatilityRegime.LOW, 6, 0),
    ],
)
@pytest.mark.asyncio
async def test_router_regime_gate_escalation(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
    regime: VolatilityRegime,
    score: int,
    expected_trader_calls: int,
) -> None:
    analyst = _Analyst(confluence_score=score)
    trader = _Trader()
    router = AgentRouter(_Scout(), analyst, trader)
    provider = _Provider(
        candle,
        indicators,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
        regime,
    )

    await router.run("BTCUSDT", provider)

    assert analyst.call_count == 1
    assert trader.call_count == expected_trader_calls


@pytest.mark.asyncio
async def test_router_logs_regime_gate_decision(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    analyst = _Analyst(confluence_score=8)
    trader = _Trader()
    router = AgentRouter(_Scout(), analyst, trader)
    provider = _Provider(
        candle,
        indicators,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
        VolatilityRegime.EXTREME,
    )

    with caplog.at_level(logging.INFO):
        await router.run("BTCUSDT", provider)

    gate_logs = [
        r for r in caplog.records if "Analyst regime gate" in r.message
    ]
    assert len(gate_logs) == 1
    record = gate_logs[0]
    assert record.confluence_score == 8
    assert record.confluence_gate == 8
    assert record.volatility_regime == "EXTREME"
