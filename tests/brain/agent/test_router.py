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
            reasoning="Test",
        )


class DummyTrader:
    async def run(self, deps, analyst_result=None):
        return TradeDecisionSchema(
            action="WAIT",
            confidence=0.5,
            reasoning="Test",
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
            position_management=None,
            calibrated_confidence=None,
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
    scout, analyst, trader = await router.run(scout_deps, analyst_deps, trader_deps)
    assert scout.verdict == "SKIP", "Expected scout to skip."
    assert analyst is None, "Expected analyst to be skipped."
    assert trader is None, "Expected trader to be skipped."


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
    scout, analyst, trader = await router.run(scout_deps, analyst_deps, trader_deps)
    assert scout.verdict == "INTERESTING", "Expected scout interest."
    assert analyst is not None, "Expected analyst result."
    assert trader is None, "Expected trader to be skipped."


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
    _scout, _analyst, trader = await router.run(scout_deps, analyst_deps, trader_deps)
    assert trader is not None, "Expected trader result."
