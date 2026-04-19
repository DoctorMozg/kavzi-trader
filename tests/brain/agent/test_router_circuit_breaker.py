from decimal import Decimal

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

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

_ANALYST_REASONING = (
    "EMA alignment is bullish with EMA20 above EMA50 above EMA200. RSI at 55 supports"
    " continuation. Volume confirms the breakout. Volatility regime is NORMAL."
)
_TRADER_REASONING = (
    "Mixed signals across all timeframes. EMA alignment is neutral and RSI is flat"
    " at 50. No clear directional bias to justify a trade entry at this time."
)


class _Scout:
    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        return ScoutDecisionSchema(
            verdict="INTERESTING",
            reason="test",
            pattern_detected=None,
        )


class _Analyst:
    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        return AnalystDecisionSchema(
            setup_valid=True,
            direction="LONG",
            confluence_score=8,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        )


class _FailingTrader:
    """Always raises UnexpectedModelBehavior — drives the circuit open."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
        scout_pattern: str | None = None,
    ) -> TradeDecisionSchema:
        self.call_count += 1
        raise UnexpectedModelBehavior("boom", body="malformed")


class _SuccessTrader:
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
            confidence=0.5,
            reasoning=_TRADER_REASONING,
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
        )


class _Provider:
    def __init__(self, scout_deps, analyst_deps, trader_deps) -> None:
        self._scout_deps = scout_deps
        self._analyst_deps = analyst_deps
        self._trader_deps = trader_deps

    def indicators_available(self, symbol: str) -> bool:
        return True

    async def get_scout(self, symbol: str):
        return self._scout_deps

    async def get_analyst(self, symbol: str):
        return self._analyst_deps

    async def get_trader(self, symbol: str):
        return self._trader_deps

    def clear_cycle_cache(self) -> None:
        pass


def _build_provider(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> _Provider:
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
    return _Provider(scout_deps, analyst_deps, trader_deps)


def test_record_trader_validation_failure_increments_counter() -> None:
    router = AgentRouter(_Scout(), _Analyst(), _SuccessTrader())
    assert router.is_trader_circuit_open("BTCUSDT") is False

    for expected in (1, 2):
        assert router.record_trader_validation_failure("BTCUSDT") == expected
    assert router.is_trader_circuit_open("BTCUSDT") is False


def test_circuit_opens_at_threshold() -> None:
    router = AgentRouter(
        _Scout(),
        _Analyst(),
        _SuccessTrader(),
        trader_circuit_threshold=2,
    )
    router.record_trader_validation_failure("BTCUSDT")
    assert router.is_trader_circuit_open("BTCUSDT") is False
    router.record_trader_validation_failure("BTCUSDT")
    assert router.is_trader_circuit_open("BTCUSDT") is True


@pytest.mark.asyncio
async def test_unexpected_model_behavior_increments_failure_counter(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    # Within a single bar the Trader dedup cache short-circuits repeats, so we
    # assert that one UnexpectedModelBehavior increments the counter exactly
    # once. Cross-bar accumulation to threshold is covered by the direct-call
    # counter tests above.
    failing = _FailingTrader()
    router = AgentRouter(
        _Scout(),
        _Analyst(),
        failing,
        trader_circuit_threshold=5,
    )
    provider = _build_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )

    await router.run("BTCUSDT", provider)
    assert failing.call_count == 1
    assert router._trader_validation_failures["BTCUSDT"] == 1


@pytest.mark.asyncio
async def test_open_circuit_skips_trader_llm(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    failing = _FailingTrader()
    router = AgentRouter(
        _Scout(),
        _Analyst(),
        failing,
        trader_circuit_threshold=2,
    )
    provider = _build_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    # Pre-seed to threshold so circuit is already open on this run
    router.record_trader_validation_failure("BTCUSDT")
    router.record_trader_validation_failure("BTCUSDT")
    assert router.is_trader_circuit_open("BTCUSDT")

    result = await router.run("BTCUSDT", provider)
    assert failing.call_count == 0, "Trader LLM called while circuit was open"
    assert result.trader is not None
    assert result.trader.action == "WAIT"
    assert "circuit breaker" in result.trader.reasoning.lower()
    assert result.trader_deps is not None


@pytest.mark.asyncio
async def test_successful_decision_resets_circuit(
    candle,
    indicators,
    volatility_regime,
    order_flow,
    algorithm_confluence,
    account_state,
    positions,
) -> None:
    router = AgentRouter(
        _Scout(),
        _Analyst(),
        _SuccessTrader(),
        trader_circuit_threshold=3,
    )
    provider = _build_provider(
        candle,
        indicators,
        volatility_regime,
        order_flow,
        algorithm_confluence,
        account_state,
        positions,
    )
    # Pre-load with 2 failures (below threshold)
    router.record_trader_validation_failure("BTCUSDT")
    router.record_trader_validation_failure("BTCUSDT")

    result = await router.run("BTCUSDT", provider)
    assert result.trader is not None
    assert result.trader.action == "WAIT"
    # Counter must be cleared after a successful Trader decision
    assert router.is_trader_circuit_open("BTCUSDT") is False
    assert router._trader_validation_failures.get("BTCUSDT", 0) == 0
