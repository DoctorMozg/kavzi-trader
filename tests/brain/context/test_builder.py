import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.schemas.analyst import (
    AnalystDecisionSchema,
    KeyLevelsSchema,
)
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.events.store import RedisEventStore


def test_context_builder_scout(candle, indicators, volatility_regime) -> None:
    deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_scout_context(deps)
    assert "market_snapshot_json" in context, "Expected market snapshot JSON."
    assert "market_snapshot" in context, "Expected structured market snapshot dict."
    assert context["market_snapshot"]["symbol"] == "BTCUSDT"


def test_context_builder_scout_logs_recent_candle_count(
    caplog,
    candle,
    indicators,
    volatility_regime,
) -> None:
    deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()

    with caplog.at_level(logging.DEBUG):
        builder.build_scout_context(deps)

    assert (
        "Built scout context for BTCUSDT: context_keys=2 recent_candles=1"
        in caplog.text
    )


def test_context_builder_analyst(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
) -> None:
    deps = AnalystDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=algorithm_confluence,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_analyst_context(deps)
    assert context["order_flow_json"] is not None, "Expected order flow JSON."
    assert "algorithm_confluence" in context, "Expected structured confluence dict."
    assert "market_snapshot" in context, "Expected structured market snapshot dict."


def test_context_builder_trader(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
    positions,
) -> None:
    deps = TradingDependenciesSchema(
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
    builder = ContextBuilder()
    context = builder.build_trader_context(deps)
    assert context["account_state_json"] is not None, "Expected account state JSON."
    assert "account_state" in context, "Expected structured account state dict."
    assert "analyst_result_json" in context, "Expected analyst result key."
    assert context["analyst_result_json"] is None, (
        "Expected None without analyst result."
    )


def test_context_builder_trader_with_analyst_result(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
    account_state,
    positions,
) -> None:
    deps = TradingDependenciesSchema(
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
    analyst_result = AnalystDecisionSchema(
        setup_valid=True,
        direction="LONG",
        confluence_score=8,
        key_levels=KeyLevelsSchema(levels=[]),
        reasoning="Test analyst result",
    )
    builder = ContextBuilder()
    context = builder.build_trader_context(deps, analyst_result=analyst_result)
    assert context["analyst_result_json"] is not None, "Expected analyst result JSON."
    assert "LONG" in context["analyst_result_json"]
