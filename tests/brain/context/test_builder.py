from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.events.store import RedisEventStore

from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)


def test_context_builder_scout(candle, indicators, volatility_regime) -> None:
    deps = ScoutDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal("105"),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        volatility_regime=volatility_regime,
    )
    builder = ContextBuilder()
    context = builder.build_scout_context(deps)
    assert "market_snapshot_json" in context, "Expected market snapshot JSON."


def test_context_builder_analyst(
    candle,
    indicators,
    order_flow,
    algorithm_confluence,
    volatility_regime,
) -> None:
    deps = AnalystDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal("105"),
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
        current_price=Decimal("105"),
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
