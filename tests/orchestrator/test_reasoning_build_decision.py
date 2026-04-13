from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
    DualConfluenceSchema,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import AccountStateSchema

_VALID_REASONING = (
    "Strong multi-factor setup with EMAs aligned, RSI neutral-bullish, and volume"
    " confirming direction. Entry at support with clear invalidation above recent"
    " swing low. Target set at the next resistance zone."
)


def _build_deps() -> TradingDependenciesSchema:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    candle = CandlestickSchema(
        open_time=now,
        open_price=Decimal(100),
        high_price=Decimal(110),
        low_price=Decimal(95),
        close_price=Decimal(105),
        volume=Decimal(1),
        close_time=now,
        quote_volume=Decimal(1),
        trades_count=1,
        taker_buy_base_volume=Decimal("0.5"),
        taker_buy_quote_volume=Decimal("0.5"),
        interval="15m",
        symbol="BTCUSDT",
    )
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(100),
        ema_50=Decimal(100),
        ema_200=Decimal(100),
        sma_20=Decimal(100),
        rsi_14=Decimal(50),
        macd=None,
        bollinger=None,
        atr_14=Decimal(2),
        volume=None,
        timestamp=now,
    )
    order_flow = OrderFlowSchema(
        symbol="BTCUSDT",
        timestamp=now,
        funding_rate=Decimal("0.0"),
        funding_zscore=Decimal("0.0"),
        next_funding_time=now,
        open_interest=Decimal(1),
        oi_change_1h_percent=Decimal(0),
        oi_change_24h_percent=Decimal(0),
        long_short_ratio=Decimal(1),
        long_account_percent=Decimal("0.5"),
        short_account_percent=Decimal("0.5"),
    )
    zero_conf = AlgorithmConfluenceSchema(
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
    account_state = AccountStateSchema(
        total_balance_usdt=Decimal(1000),
        available_balance_usdt=Decimal(1000),
        locked_balance_usdt=Decimal(0),
        unrealized_pnl=Decimal(0),
        peak_balance=Decimal(1000),
        current_drawdown_percent=Decimal(0),
        updated_at=now,
    )
    return TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal(105),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=DualConfluenceSchema(
            long=zero_conf,
            short=zero_conf,
            detected_side="LONG",
        ),
        volatility_regime=VolatilityRegime.NORMAL,
        account_state=account_state,
        open_positions=[],
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )


def _build_loop(router: MagicMock) -> ReasoningLoop:
    return ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=MagicMock(),
        redis_client=AsyncMock(),
        interval_s=1,
    )


def test_build_decision_message_valid_long_returns_schema() -> None:
    deps = _build_deps()
    trader = TradeDecisionSchema(
        action="LONG",
        confidence=0.8,
        reasoning=_VALID_REASONING,
        suggested_entry=Decimal(105),
        suggested_stop_loss=Decimal(95),
        suggested_take_profit=Decimal(125),
    )
    router = MagicMock()
    loop = _build_loop(router)

    message = loop._build_decision_message(trader, deps, snapshot_at_ms=1_000)

    assert message is not None
    assert message.action == "LONG"
    # Risk validator computes the actual size; we must NOT prefill a zero
    # quantity that the translator would sniff and accept as valid.
    assert message.quantity is None
    router.record_trader_validation_failure.assert_not_called()


def test_build_decision_message_rejects_long_missing_stop() -> None:
    deps = _build_deps()
    # model_construct bypasses TradeDecisionSchema validation so we can
    # simulate a malformed upstream output slipping past the schema — the
    # boundary guard in ReasoningLoop must still reject it.
    trader = TradeDecisionSchema.model_construct(
        action="LONG",
        confidence=0.8,
        reasoning=_VALID_REASONING,
        suggested_entry=Decimal(105),
        suggested_stop_loss=None,
        suggested_take_profit=Decimal(125),
    )
    router = MagicMock()
    loop = _build_loop(router)

    message = loop._build_decision_message(trader, deps, snapshot_at_ms=1_000)

    assert message is None
    router.record_trader_validation_failure.assert_called_once_with("BTCUSDT")


def test_build_decision_message_rejects_short_missing_take_profit() -> None:
    deps = _build_deps()
    trader = TradeDecisionSchema.model_construct(
        action="SHORT",
        confidence=0.6,
        reasoning=_VALID_REASONING,
        suggested_entry=Decimal(105),
        suggested_stop_loss=Decimal(115),
        suggested_take_profit=None,
    )
    router = MagicMock()
    loop = _build_loop(router)

    message = loop._build_decision_message(trader, deps, snapshot_at_ms=1_000)

    assert message is None
    router.record_trader_validation_failure.assert_called_once_with("BTCUSDT")


def test_build_decision_message_close_allows_missing_geometry() -> None:
    # CLOSE decisions legitimately carry no entry/stop/tp geometry and must
    # not be treated as malformed.
    deps = _build_deps()
    trader = TradeDecisionSchema.model_construct(
        action="CLOSE",
        confidence=0.9,
        reasoning=_VALID_REASONING,
        suggested_entry=None,
        suggested_stop_loss=None,
        suggested_take_profit=None,
    )
    router = MagicMock()
    loop = _build_loop(router)

    message = loop._build_decision_message(trader, deps, snapshot_at_ms=1_000)

    assert message is not None
    assert message.action == "CLOSE"
    router.record_trader_validation_failure.assert_not_called()
