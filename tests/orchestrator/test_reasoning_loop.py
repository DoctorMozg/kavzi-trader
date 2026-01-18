import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema, KeyLevelsSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import AccountStateSchema


class DummyDepsProvider:
    def __init__(self, deps: TradingDependenciesSchema) -> None:
        self._deps = deps

    async def get_scout(self, symbol: str) -> ScoutDependenciesSchema:
        return ScoutDependenciesSchema(
            symbol=symbol,
            current_price=self._deps.current_price,
            timeframe=self._deps.timeframe,
            recent_candles=self._deps.recent_candles,
            indicators=self._deps.indicators,
            volatility_regime=self._deps.volatility_regime,
        )

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        return AnalystDependenciesSchema(
            symbol=symbol,
            current_price=self._deps.current_price,
            timeframe=self._deps.timeframe,
            recent_candles=self._deps.recent_candles,
            indicators=self._deps.indicators,
            order_flow=self._deps.order_flow,
            algorithm_confluence=self._deps.algorithm_confluence,
            volatility_regime=self._deps.volatility_regime,
        )

    async def get_trader(self, symbol: str) -> TradingDependenciesSchema:
        return self._deps


def _build_deps() -> TradingDependenciesSchema:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    candle = CandlestickSchema(
        open_time=now,
        open_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("95"),
        close_price=Decimal("105"),
        volume=Decimal("1"),
        close_time=now,
        quote_volume=Decimal("1"),
        trades_count=1,
        taker_buy_base_volume=Decimal("0.5"),
        taker_buy_quote_volume=Decimal("0.5"),
        interval="15m",
        symbol="BTCUSDT",
    )
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal("100"),
        ema_50=Decimal("100"),
        ema_200=Decimal("100"),
        sma_20=Decimal("100"),
        rsi_14=Decimal("50"),
        macd=None,
        bollinger=None,
        atr_14=Decimal("2"),
        volume=None,
        timestamp=now,
    )
    order_flow = OrderFlowSchema(
        symbol="BTCUSDT",
        timestamp=now,
        funding_rate=Decimal("0.0"),
        funding_zscore=Decimal("0.0"),
        next_funding_time=now,
        open_interest=Decimal("1"),
        oi_change_1h_percent=Decimal("0"),
        oi_change_24h_percent=Decimal("0"),
        long_short_ratio=Decimal("1"),
        long_account_percent=Decimal("0.5"),
        short_account_percent=Decimal("0.5"),
    )
    confluence = AlgorithmConfluenceSchema(
        ema_alignment=False,
        rsi_favorable=False,
        volume_above_average=False,
        price_at_bollinger=False,
        funding_favorable=False,
        oi_supports_direction=False,
        score=5,
    )
    account_state = AccountStateSchema(
        total_balance_usdt=Decimal("1000"),
        available_balance_usdt=Decimal("1000"),
        locked_balance_usdt=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        peak_balance=Decimal("1000"),
        current_drawdown_percent=Decimal("0"),
        updated_at=now,
    )
    return TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal("105"),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=confluence,
        volatility_regime=VolatilityRegime.NORMAL,
        account_state=account_state,
        open_positions=[],
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )


@pytest.mark.asyncio()
async def test_reasoning_loop_enqueues_decision() -> None:
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(
        return_value=(
            ScoutDecisionSchema(
                verdict="INTERESTING",
                reason="ok",
                pattern_detected=None,
            ),
            AnalystDecisionSchema(
                setup_valid=True,
                direction="LONG",
                confluence_score=7,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning="ok",
            ),
            TradeDecisionSchema(
                action="BUY",
                confidence=0.8,
                reasoning="go",
                suggested_entry=Decimal("105"),
                suggested_stop_loss=Decimal("95"),
                suggested_take_profit=Decimal("120"),
                position_management=None,
                calibrated_confidence=0.7,
            ),
        ),
    )
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=1,
    )

    task = asyncio.create_task(loop.run())
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    redis_client.client.lpush.assert_called_once()
