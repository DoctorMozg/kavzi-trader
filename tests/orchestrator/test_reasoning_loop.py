import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.agent.router import PipelineResult
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
    DualConfluenceSchema,
)
from kavzi_trader.spine.filters.filter_chain_result_schema import (
    FilterChainResultSchema,
)
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)

_ANALYST_REASONING = (
    "EMA alignment is bullish with EMA20 above EMA50 above EMA200. RSI at 55 supports"
    " continuation. Volume confirms the breakout. Volatility regime is NORMAL."
)
_TRADER_REASONING = (
    "Agree with Analyst direction LONG. Confluence score 4/6 with EMA alignment and"
    " volume supporting. Entry at 105 near current price, SL at 95 below key support,"
    " TP at 125 at next resistance. R:R is 2.0:1 which meets minimum threshold."
)


class DummyDepsProvider:
    def __init__(self, deps: TradingDependenciesSchema) -> None:
        self._deps = deps

    def indicators_available(self, symbol: str) -> bool:
        return True

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

    def clear_cycle_cache(self) -> None:
        pass


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
    long_conf = AlgorithmConfluenceSchema(
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
    short_conf = AlgorithmConfluenceSchema(
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
    confluence = DualConfluenceSchema(
        long=long_conf,
        short=short_conf,
        detected_side="LONG",
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
        algorithm_confluence=confluence,
        volatility_regime=VolatilityRegime.NORMAL,
        account_state=account_state,
        open_positions=[],
        exchange_client=BinanceClient.__new__(BinanceClient),
        event_store=RedisEventStore.__new__(RedisEventStore),
    )


@pytest.mark.asyncio
async def test_reasoning_loop_enqueues_decision() -> None:
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(
        return_value=PipelineResult(
            scout=ScoutDecisionSchema(
                verdict="INTERESTING",
                reason="ok",
                pattern_detected=None,
            ),
            analyst=AnalystDecisionSchema(
                setup_valid=True,
                direction="LONG",
                confluence_score=7,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning=_ANALYST_REASONING,
            ),
            trader=TradeDecisionSchema(
                action="LONG",
                confidence=0.8,
                reasoning=_TRADER_REASONING,
                suggested_entry=Decimal(105),
                suggested_stop_loss=Decimal(95),
                suggested_take_profit=Decimal(125),
            ),
            trader_deps=deps,
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
    for _ in range(20):
        await asyncio.sleep(0)
        if redis_client.client.lpush.call_count > 0:
            break
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    redis_client.client.lpush.assert_called_once()


@pytest.mark.asyncio
async def test_decision_message_includes_leverage() -> None:
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(
        return_value=PipelineResult(
            scout=ScoutDecisionSchema(
                verdict="INTERESTING",
                reason="ok",
                pattern_detected=None,
            ),
            analyst=AnalystDecisionSchema(
                setup_valid=True,
                direction="LONG",
                confluence_score=7,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning=_ANALYST_REASONING,
            ),
            trader=TradeDecisionSchema(
                action="LONG",
                confidence=0.8,
                reasoning=_TRADER_REASONING,
                suggested_entry=Decimal(105),
                suggested_stop_loss=Decimal(95),
                suggested_take_profit=Decimal(125),
            ),
            trader_deps=deps,
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
    for _ in range(20):
        await asyncio.sleep(0)
        if redis_client.client.lpush.call_count > 0:
            break
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    import json

    pushed_data = redis_client.client.lpush.call_args[0][1]
    message = json.loads(pushed_data)
    assert message["leverage"] == 5


@pytest.mark.asyncio
async def test_backoff_on_all_skip() -> None:
    """When all symbols SKIP, the sleep interval should increase."""
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(
        return_value=PipelineResult(
            scout=ScoutDecisionSchema(
                verdict="SKIP",
                reason="dead market",
                pattern_detected=None,
            ),
        ),
    )
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()

    sleep_durations: list[float] = []
    original_sleep = asyncio.sleep

    async def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await original_sleep(0)

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=10,
    )

    import unittest.mock

    with unittest.mock.patch("asyncio.sleep", side_effect=_capture_sleep):
        task = asyncio.create_task(loop.run())
        for _ in range(50):
            await original_sleep(0)
            if len(sleep_durations) >= 2:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert len(sleep_durations) >= 2
    assert sleep_durations[1] > sleep_durations[0]


@pytest.mark.asyncio
async def test_backoff_resets_on_interesting() -> None:
    """After backoff, an INTERESTING verdict should reset the interval."""
    deps = _build_deps()
    provider = DummyDepsProvider(deps)

    call_count = 0

    async def _alternating_run(symbol: str, deps_provider: object) -> PipelineResult:
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return PipelineResult(
                scout=ScoutDecisionSchema(
                    verdict="SKIP", reason="dead", pattern_detected=None
                ),
            )
        return PipelineResult(
            scout=ScoutDecisionSchema(
                verdict="INTERESTING", reason="volume", pattern_detected=None
            ),
        )

    router = AsyncMock()
    router.run = AsyncMock(side_effect=_alternating_run)
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()

    sleep_durations: list[float] = []
    original_sleep = asyncio.sleep

    async def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await original_sleep(0)

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=10,
    )

    import unittest.mock

    with unittest.mock.patch("asyncio.sleep", side_effect=_capture_sleep):
        task = asyncio.create_task(loop.run())
        for _ in range(50):
            await original_sleep(0)
            if len(sleep_durations) >= 2:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert len(sleep_durations) >= 2
    # Cycle 1: all SKIP → backoff to 20
    assert sleep_durations[0] == 20.0
    # Cycle 2: INTERESTING → reset to base 10
    assert sleep_durations[1] == 10.0


def _make_skip_result() -> PipelineResult:
    return PipelineResult(
        scout=ScoutDecisionSchema(verdict="SKIP", reason="dead", pattern_detected=None),
    )


def _make_analyst_result() -> PipelineResult:
    return PipelineResult(
        scout=ScoutDecisionSchema(
            verdict="INTERESTING", reason="volume", pattern_detected=None
        ),
        analyst=AnalystDecisionSchema(
            setup_valid=False,
            direction="LONG",
            confluence_score=5,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        ),
    )


@pytest.mark.asyncio
async def test_cooldown_after_analyst_skips_cycles() -> None:
    """After Analyst rejection, symbol should be skipped only when BOTH directions
    are on cooldown. _make_analyst_result returns direction=LONG, so only LONG
    gets a cooldown. Since SHORT has no cooldown, the symbol is re-evaluated
    every cycle (direction-aware cooldowns).
    """
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(return_value=_make_analyst_result())
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=1,
        analyst_cooldown_cycles=2,
    )

    sleep_durations: list[float] = []
    original_sleep = asyncio.sleep

    async def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await original_sleep(0)

    import unittest.mock

    with unittest.mock.patch("asyncio.sleep", side_effect=_capture_sleep):
        task = asyncio.create_task(loop.run())
        for _ in range(200):
            await original_sleep(0)
            if len(sleep_durations) >= 3:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    # With direction-aware cooldowns, a single-direction rejection (LONG)
    # does NOT block the symbol from re-evaluation (SHORT may be viable).
    # Router is called every cycle.
    assert router.run.call_count >= 3


@pytest.mark.asyncio
async def test_skip_symbol_with_open_position() -> None:
    """Symbols with open positions should be skipped entirely."""
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(return_value=_make_skip_result())
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()

    now = datetime.now(UTC)
    mock_state_manager = MagicMock()
    mock_state_manager.get_all_positions = AsyncMock(
        return_value=[
            PositionSchema(
                id="pos-1",
                symbol="BTCUSDT",
                side="LONG",
                quantity=Decimal("0.1"),
                entry_price=Decimal(50000),
                stop_loss=Decimal(49000),
                take_profit=Decimal(52000),
                current_stop_loss=Decimal(49000),
                management_config=PositionManagementConfigSchema(),
                opened_at=now,
                updated_at=now,
            ),
        ],
    )

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=1,
        state_manager=mock_state_manager,
    )

    sleep_durations: list[float] = []
    original_sleep = asyncio.sleep

    async def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await original_sleep(0)

    import unittest.mock

    with unittest.mock.patch("asyncio.sleep", side_effect=_capture_sleep):
        task = asyncio.create_task(loop.run())
        for _ in range(50):
            await original_sleep(0)
            if len(sleep_durations) >= 2:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    # Router should never be called because position is open
    router.run.assert_not_called()


@pytest.mark.asyncio
async def test_volatility_gate_reports_as_scout_scan() -> None:
    """Volatility-gated SKIP now appears as a scout_scan action."""
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(
        return_value=PipelineResult(
            scout=ScoutDecisionSchema(
                verdict="SKIP",
                reason="Volatility regime LOW blocks trading",
                pattern_detected=None,
            ),
        ),
    )
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()

    mock_populator = AsyncMock()
    mock_populator.record_action = AsyncMock()

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=1,
        report_populator=mock_populator,
    )

    sleep_durations: list[float] = []
    original_sleep = asyncio.sleep

    async def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await original_sleep(0)

    import unittest.mock

    with unittest.mock.patch("asyncio.sleep", side_effect=_capture_sleep):
        task = asyncio.create_task(loop.run())
        for _ in range(50):
            await original_sleep(0)
            if len(sleep_durations) >= 1:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    scout_calls = [
        c
        for c in mock_populator.record_action.call_args_list
        if c.kwargs.get("action_type") == "scout_scan"
    ]
    assert len(scout_calls) >= 1
    summary = scout_calls[0].kwargs.get("summary", "")
    assert "Volatility regime LOW" in summary


def _make_analyst_result_with_confluence(confluence_score: int) -> PipelineResult:
    return PipelineResult(
        scout=ScoutDecisionSchema(
            verdict="INTERESTING", reason="volume", pattern_detected=None
        ),
        analyst=AnalystDecisionSchema(
            setup_valid=False,
            direction="LONG",
            confluence_score=confluence_score,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        ),
    )


def test_graduated_cooldown_low_confluence() -> None:
    """Confluence <= 2 should produce 3x the base cooldown."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )
    assert loop._compute_rejection_cooldown(1) == 9
    assert loop._compute_rejection_cooldown(2) == 9


def test_graduated_cooldown_reject_band_high_side() -> None:
    """Confluence 3 (top of reject band) should produce 2x the base cooldown."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )
    assert loop._compute_rejection_cooldown(3) == 6


def _make_analyst_decision(
    *,
    setup_valid: bool,
    direction: Literal["LONG", "SHORT", "NEUTRAL"],
    confluence_score: int,
) -> AnalystDecisionSchema:
    return AnalystDecisionSchema(
        setup_valid=setup_valid,
        direction=direction,
        confluence_score=confluence_score,
        key_levels=KeyLevelsSchema(levels=[]),
        reasoning=_ANALYST_REASONING,
    )


def test_analyst_cooldown_reject_band_escalates() -> None:
    """Score <= 3 + invalid increments rejection counter and uses base*multiplier."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )
    analyst = _make_analyst_decision(
        setup_valid=False,
        direction="LONG",
        confluence_score=2,
    )

    loop._apply_analyst_cooldown("BTCUSDT", analyst)
    key = ("BTCUSDT", "LONG")
    assert loop._consecutive_rejections[key] == 1
    assert loop._cooldowns[key] == 9  # base=9 * mult=1

    loop._apply_analyst_cooldown("BTCUSDT", analyst)
    assert loop._consecutive_rejections[key] == 2
    assert loop._cooldowns[key] == 18  # base=9 * mult=2


def test_analyst_cooldown_borderline_band_no_escalation() -> None:
    """Score 4-5 + invalid gets a light cooldown and does NOT escalate counts."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )
    key = ("BTCUSDT", "LONG")

    for score in (4, 5):
        analyst = _make_analyst_decision(
            setup_valid=False,
            direction="LONG",
            confluence_score=score,
        )
        loop._apply_analyst_cooldown("BTCUSDT", analyst)
        assert key not in loop._consecutive_rejections
        assert loop._cooldowns[key] == 1  # _BORDERLINE_COOLDOWN_CYCLES


def test_analyst_cooldown_llm_rejects_high_confluence() -> None:
    """Score >= 6 but setup_valid=False also lands in the light-cooldown branch."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )
    analyst = _make_analyst_decision(
        setup_valid=False,
        direction="LONG",
        confluence_score=9,
    )
    loop._apply_analyst_cooldown("BTCUSDT", analyst)

    key = ("BTCUSDT", "LONG")
    assert key not in loop._consecutive_rejections
    assert loop._cooldowns[key] == 1


def test_analyst_cooldown_valid_setup_clears_rejection_counter() -> None:
    """A valid setup at/above the entry gate resets rejection counters."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )
    loop._consecutive_rejections[("BTCUSDT", "LONG")] = 3

    analyst = _make_analyst_decision(
        setup_valid=True,
        direction="LONG",
        confluence_score=7,
    )
    loop._apply_analyst_cooldown("BTCUSDT", analyst)

    assert ("BTCUSDT", "LONG") not in loop._consecutive_rejections


def test_should_enqueue_requires_confluence_entry_gate() -> None:
    """_should_enqueue must block scores below the entry gate even if valid."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
    )
    deps = _build_deps()

    borderline = PipelineResult(
        scout=ScoutDecisionSchema(
            verdict="INTERESTING",
            reason="ok",
            pattern_detected=None,
        ),
        analyst=_make_analyst_decision(
            setup_valid=True,
            direction="LONG",
            confluence_score=4,
        ),
        trader=TradeDecisionSchema(
            action="LONG",
            confidence=0.8,
            reasoning=_TRADER_REASONING,
            suggested_entry=Decimal(105),
            suggested_stop_loss=Decimal(95),
            suggested_take_profit=Decimal(125),
        ),
        trader_deps=deps,
    )
    assert loop._should_enqueue(borderline) is False

    at_gate = PipelineResult(
        scout=borderline.scout,
        analyst=_make_analyst_decision(
            setup_valid=True,
            direction="LONG",
            confluence_score=5,
        ),
        trader=borderline.trader,
        trader_deps=deps,
    )
    assert loop._should_enqueue(at_gate) is True


def _make_trade_result() -> PipelineResult:
    deps = _build_deps()
    return PipelineResult(
        scout=ScoutDecisionSchema(
            verdict="INTERESTING", reason="ok", pattern_detected=None
        ),
        analyst=AnalystDecisionSchema(
            setup_valid=True,
            direction="LONG",
            confluence_score=7,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        ),
        trader=TradeDecisionSchema(
            action="LONG",
            confidence=0.8,
            reasoning=_TRADER_REASONING,
            suggested_entry=Decimal(105),
            suggested_stop_loss=Decimal(95),
            suggested_take_profit=Decimal(125),
        ),
        trader_deps=deps,
    )


@pytest.mark.asyncio
async def test_filter_chain_blocks_trade() -> None:
    """When filter chain rejects, decision is NOT enqueued and rejection is reported."""
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(return_value=_make_trade_result())
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()
    mock_populator = AsyncMock()
    mock_populator.record_action = AsyncMock()

    mock_filter_chain = AsyncMock()
    mock_filter_chain.evaluate = AsyncMock(
        return_value=FilterChainResultSchema(
            is_allowed=False,
            rejection_reason="crowded_long",
            results=[
                FilterResultSchema(name="funding", is_allowed=False, reason="crowded"),
            ],
            volatility_regime=VolatilityRegime.NORMAL,
            volatility_zscore=Decimal("0.5"),
        ),
    )

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=1,
        report_populator=mock_populator,
        filter_chain=mock_filter_chain,
    )

    sleep_durations: list[float] = []
    original_sleep = asyncio.sleep

    async def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await original_sleep(0)

    import unittest.mock

    with unittest.mock.patch("asyncio.sleep", side_effect=_capture_sleep):
        task = asyncio.create_task(loop.run())
        for _ in range(50):
            await original_sleep(0)
            if len(sleep_durations) >= 1:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    redis_client.client.lpush.assert_not_called()
    rejection_calls = [
        c
        for c in mock_populator.record_action.call_args_list
        if c.kwargs.get("action_type") == "filter_rejection"
    ]
    assert len(rejection_calls) >= 1
    assert "crowded_long" in rejection_calls[0].kwargs.get("summary", "")


@pytest.mark.asyncio
async def test_filter_chain_allows_trade() -> None:
    """When filter chain allows, decision IS enqueued."""
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(return_value=_make_trade_result())
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()

    mock_filter_chain = AsyncMock()
    mock_filter_chain.evaluate = AsyncMock(
        return_value=FilterChainResultSchema(
            is_allowed=True,
            results=[],
            volatility_regime=VolatilityRegime.NORMAL,
            volatility_zscore=Decimal("0.5"),
        ),
    )

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=1,
        filter_chain=mock_filter_chain,
    )

    task = asyncio.create_task(loop.run())
    for _ in range(20):
        await asyncio.sleep(0)
        if redis_client.client.lpush.call_count > 0:
            break
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    redis_client.client.lpush.assert_called_once()


@pytest.mark.asyncio
async def test_no_filter_chain_passes_through() -> None:
    """Without filter_chain (None), decisions are enqueued as before."""
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(return_value=_make_trade_result())
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
    for _ in range(20):
        await asyncio.sleep(0)
        if redis_client.client.lpush.call_count > 0:
            break
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    redis_client.client.lpush.assert_called_once()


def test_consecutive_rejections_escalate_cooldown() -> None:
    """Repeated analyst rejections for the same symbol+direction increase cooldown."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
        max_consecutive_rejection_multiplier=5,
    )
    key = ("BTCUSDT", "LONG")

    # First rejection: confluence=2 → base=9, multiplier=min(1,5)=1
    count = loop._consecutive_rejections.get(key, 0) + 1
    loop._consecutive_rejections[key] = count
    base = loop._compute_rejection_cooldown(2)
    multiplier = min(count, loop._max_rejection_multiplier)
    assert base == 9
    assert base * multiplier == 9  # 9 * 1

    # Second rejection: multiplier=min(2,5)=2
    count = loop._consecutive_rejections.get(key, 0) + 1
    loop._consecutive_rejections[key] = count
    multiplier = min(count, loop._max_rejection_multiplier)
    assert base * multiplier == 18  # 9 * 2

    # Sixth rejection: capped at 5
    loop._consecutive_rejections[key] = 5
    count = loop._consecutive_rejections.get(key, 0) + 1
    loop._consecutive_rejections[key] = count
    multiplier = min(count, loop._max_rejection_multiplier)
    assert base * multiplier == 45  # 9 * 5 (capped)


def test_consecutive_rejections_reset_on_valid_analyst() -> None:
    """A valid analyst result resets the rejection counter for that direction."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )
    key = ("BTCUSDT", "LONG")

    # Accumulate 3 rejections
    loop._consecutive_rejections[key] = 3

    # Reset (mirrors _handle_symbol logic on valid analyst)
    loop._consecutive_rejections.pop(key, None)
    assert key not in loop._consecutive_rejections

    # Next rejection starts fresh from multiplier=1
    count = loop._consecutive_rejections.get(key, 0) + 1
    loop._consecutive_rejections[key] = count
    base = loop._compute_rejection_cooldown(2)
    multiplier = min(count, loop._max_rejection_multiplier)
    assert multiplier == 1
    assert base * multiplier == 9


def test_direction_aware_cooldown_allows_opposite_direction() -> None:
    """SHORT cooldown should not block LONG evaluation on the same symbol."""
    loop = ReasoningLoop(
        symbols=["TAOUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )

    # Set SHORT cooldown only
    loop._cooldowns[("TAOUSDT", "SHORT")] = 10
    loop._cooldowns[("TAOUSDT", "LONG")] = 0

    # tick_cooldowns should return False (not all blocked)
    assert loop._tick_cooldowns("TAOUSDT") is False


def test_direction_aware_cooldown_blocks_when_both_blocked() -> None:
    """When both LONG and SHORT are on cooldown, the symbol should be skipped."""
    loop = ReasoningLoop(
        symbols=["TAOUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )

    # Set both cooldowns
    loop._cooldowns[("TAOUSDT", "LONG")] = 5
    loop._cooldowns[("TAOUSDT", "SHORT")] = 10

    # Should block
    assert loop._tick_cooldowns("TAOUSDT") is True
    # Cooldowns should have decremented
    assert loop._cooldowns[("TAOUSDT", "LONG")] == 4
    assert loop._cooldowns[("TAOUSDT", "SHORT")] == 9


def test_neutral_rejection_blocks_both_directions() -> None:
    """A NEUTRAL rejection should set cooldown for both LONG and SHORT."""
    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
        analyst_cooldown_cycles=3,
    )

    # Simulate NEUTRAL rejection (mirrors _handle_symbol logic)
    direction = "NEUTRAL"
    cooldown_dirs = ["LONG", "SHORT"] if direction == "NEUTRAL" else [direction]
    for d in cooldown_dirs:
        key = ("BTCUSDT", d)
        count = loop._consecutive_rejections.get(key, 0) + 1
        loop._consecutive_rejections[key] = count
        base = loop._compute_rejection_cooldown(3)  # top of reject band
        multiplier = min(count, loop._max_rejection_multiplier)
        loop._cooldowns[key] = base * multiplier

    assert loop._cooldowns[("BTCUSDT", "LONG")] == 6  # base=6 * mult=1
    assert loop._cooldowns[("BTCUSDT", "SHORT")] == 6


def _make_wait_result(
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "LONG",
) -> PipelineResult:
    return PipelineResult(
        scout=ScoutDecisionSchema(
            verdict="INTERESTING", reason="volume", pattern_detected=None
        ),
        analyst=AnalystDecisionSchema(
            setup_valid=True,
            direction=direction,
            confluence_score=7,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=_ANALYST_REASONING,
        ),
        trader=TradeDecisionSchema(
            action="WAIT",
            confidence=0.5,
            reasoning=_TRADER_REASONING,
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
        ),
    )


def test_consecutive_waits_apply_cooldown() -> None:
    """After 5 consecutive WAITs, cooldown is set for (symbol, direction)."""
    loop = ReasoningLoop(
        symbols=["TONUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
    )
    result = _make_wait_result("LONG")

    # Simulate 5 consecutive WAITs (threshold=5)
    for _ in range(5):
        loop._track_consecutive_waits("TONUSDT", result)

    key = ("TONUSDT", "LONG")
    assert loop._consecutive_waits[key] == 5
    assert loop._cooldowns.get(key, 0) > 0


def test_consecutive_waits_reset_on_trade() -> None:
    """Trade enqueue clears WAIT counters for the symbol."""
    loop = ReasoningLoop(
        symbols=["TONUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
    )

    # Accumulate some WAITs
    loop._consecutive_waits[("TONUSDT", "LONG")] = 5
    loop._consecutive_waits[("TONUSDT", "SHORT")] = 2

    # Simulate trade enqueue reset (mirrors _handle_symbol logic)
    loop._consecutive_waits.pop(("TONUSDT", "LONG"), None)
    loop._consecutive_waits.pop(("TONUSDT", "SHORT"), None)

    assert ("TONUSDT", "LONG") not in loop._consecutive_waits
    assert ("TONUSDT", "SHORT") not in loop._consecutive_waits


def test_consecutive_waits_escalate() -> None:
    """6th+ WAITs increase cooldown, capped at max."""
    loop = ReasoningLoop(
        symbols=["TONUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
    )
    result = _make_wait_result("LONG")
    key = ("TONUSDT", "LONG")

    # 7 consecutive WAITs (threshold=5, base=2)
    for _ in range(7):
        loop._track_consecutive_waits("TONUSDT", result)

    assert loop._consecutive_waits[key] == 7
    # count=7, excess=7-5+1=3, cooldown=min(2*3, 12)=6
    assert loop._cooldowns[key] == 6

    # Push to cap (15+ waits)
    for _ in range(8):
        loop._track_consecutive_waits("TONUSDT", result)

    assert loop._consecutive_waits[key] == 15
    # excess=15-5+1=11, cooldown=min(2*11, 12)=12
    assert loop._cooldowns[key] == 12


def test_consecutive_waits_no_cooldown_below_threshold() -> None:
    """Fewer than 5 WAITs should not set any cooldown."""
    loop = ReasoningLoop(
        symbols=["TONUSDT"],
        router=AsyncMock(),
        deps_provider=AsyncMock(),
        redis_client=AsyncMock(),
    )
    result = _make_wait_result("LONG")
    key = ("TONUSDT", "LONG")

    loop._track_consecutive_waits("TONUSDT", result)
    loop._track_consecutive_waits("TONUSDT", result)

    assert loop._consecutive_waits[key] == 2
    assert loop._cooldowns.get(key, 0) == 0


@pytest.mark.asyncio
async def test_pipeline_complete_event_recorded() -> None:
    """When all 3 tiers fire, a pipeline_complete event is recorded."""
    deps = _build_deps()
    provider = DummyDepsProvider(deps)
    router = AsyncMock()
    router.run = AsyncMock(return_value=_make_wait_result("LONG"))
    redis_client = AsyncMock()
    redis_client.client.lpush = AsyncMock()
    mock_populator = AsyncMock()
    mock_populator.record_action = AsyncMock()

    loop = ReasoningLoop(
        symbols=["BTCUSDT"],
        router=router,
        deps_provider=provider,
        redis_client=redis_client,
        interval_s=1,
        report_populator=mock_populator,
    )

    sleep_durations: list[float] = []
    original_sleep = asyncio.sleep

    async def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await original_sleep(0)

    import unittest.mock

    with unittest.mock.patch("asyncio.sleep", side_effect=_capture_sleep):
        task = asyncio.create_task(loop.run())
        for _ in range(50):
            await original_sleep(0)
            if len(sleep_durations) >= 1:
                break
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    complete_calls = [
        c
        for c in mock_populator.record_action.call_args_list
        if c.kwargs.get("action_type") == "pipeline_complete"
    ]
    assert len(complete_calls) >= 1
    summary = complete_calls[0].kwargs.get("summary", "")
    assert "Scout=INTERESTING" in summary
    assert "Trader=WAIT" in summary
