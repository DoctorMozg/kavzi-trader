"""
Trading commands for the KavziTrader CLI.
"""

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

import click

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.brain.agent.analyst import AnalystAgent
from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.agent.scout import ScoutAgent
from kavzi_trader.brain.agent.trader import TraderAgent
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema, KeyLevelsSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.config import AppConfig
from kavzi_trader.events.config import EventStoreConfigSchema
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.orchestrator.config import OrchestratorConfigSchema
from kavzi_trader.orchestrator.health import HealthChecker
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.loops.order_flow import OrderFlowLoop
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop
from kavzi_trader.orchestrator.orchestrator import TradingOrchestrator
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
)
from kavzi_trader.spine.position.break_even import BreakEvenMover
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.scaling import ScaleInChecker
from kavzi_trader.spine.position.time_exit import TimeExitChecker
from kavzi_trader.spine.position.trailing import TrailingStopChecker
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.state.config import RedisConfigSchema
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import AccountStateSchema

logger = logging.getLogger(__name__)


@click.group()
def trade() -> None:
    """Trading commands."""


class _NoopStreamManager:
    async def start(self) -> None:
        await asyncio.sleep(0)


class _NoopOrderFlowFetcher:
    async def fetch(self) -> None:
        await asyncio.sleep(0)


class _NoopDepsProvider:
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
        return self._deps.model_copy(update={"symbol": symbol})


class _NoopAtrProvider:
    async def get_atr(self, _symbol: str) -> Decimal:
        return Decimal("0")


class _NoopScout:
    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        _ = deps
        return ScoutDecisionSchema(
            verdict="SKIP",
            reason="disabled",
            pattern_detected=None,
        )


class _NoopAnalyst:
    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        _ = deps
        return AnalystDecisionSchema(
            setup_valid=False,
            direction="NEUTRAL",
            confluence_score=0,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning="disabled",
        )


class _NoopTrader:
    async def run(self, deps: TradingDependenciesSchema) -> TradeDecisionSchema:
        _ = deps
        return TradeDecisionSchema(
            action="WAIT",
            confidence=0.0,
            reasoning="disabled",
            suggested_entry=None,
            suggested_stop_loss=None,
            suggested_take_profit=None,
            position_management=None,
            calibrated_confidence=0.0,
        )


def _build_state_manager(app_config: AppConfig) -> StateManager:
    redis_config = RedisConfigSchema()
    return StateManager(
        redis_config=redis_config,
        exchange_client=_build_exchange(app_config),
    )


def _build_exchange(app_config: AppConfig) -> BinanceClient:
    return BinanceClient(
        api_key=app_config.api.binance.api_key,
        api_secret=app_config.api.binance.api_secret,
        testnet=app_config.api.binance.testnet,
    )


def _build_noop_dependencies() -> TradingDependenciesSchema:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    exchange = BinanceClient(api_key="", api_secret="", testnet=True)
    event_store = RedisEventStore(
        RedisStateClient(RedisConfigSchema()),
        EventStoreConfigSchema(),
    )
    candle = CandlestickSchema(
        open_time=now,
        open_price=Decimal("100"),
        high_price=Decimal("100"),
        low_price=Decimal("100"),
        close_price=Decimal("100"),
        volume=Decimal("0"),
        close_time=now,
        quote_volume=Decimal("0"),
        trades_count=0,
        taker_buy_base_volume=Decimal("0"),
        taker_buy_quote_volume=Decimal("0"),
        interval="15m",
        symbol="BTCUSDT",
    )
    indicators = TechnicalIndicatorsSchema(
        ema_20=None,
        ema_50=None,
        ema_200=None,
        sma_20=None,
        rsi_14=None,
        macd=None,
        bollinger=None,
        atr_14=Decimal("0"),
        volume=None,
        timestamp=now,
    )
    order_flow = OrderFlowSchema(
        symbol="BTCUSDT",
        timestamp=now,
        funding_rate=Decimal("0"),
        funding_zscore=Decimal("0"),
        next_funding_time=now,
        open_interest=Decimal("0"),
        oi_change_1h_percent=Decimal("0"),
        oi_change_24h_percent=Decimal("0"),
        long_short_ratio=Decimal("0"),
        long_account_percent=Decimal("0"),
        short_account_percent=Decimal("0"),
    )
    account_state = AccountStateSchema(
        total_balance_usdt=Decimal("0"),
        available_balance_usdt=Decimal("0"),
        locked_balance_usdt=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        peak_balance=Decimal("0"),
        current_drawdown_percent=Decimal("0"),
        updated_at=now,
    )
    return TradingDependenciesSchema(
        symbol="BTCUSDT",
        current_price=Decimal("0"),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        order_flow=order_flow,
        algorithm_confluence=AlgorithmConfluenceSchema(
            ema_alignment=False,
            rsi_favorable=False,
            volume_above_average=False,
            price_at_bollinger=False,
            funding_favorable=False,
            oi_supports_direction=False,
            score=0,
        ),
        volatility_regime=VolatilityRegime.NORMAL,
        account_state=account_state,
        open_positions=[],
        exchange_client=exchange,
        event_store=event_store,
    )


async def _start_orchestrator(app_config: AppConfig) -> None:
    state_manager = _build_state_manager(app_config)
    redis_client = RedisStateClient(RedisConfigSchema())
    await redis_client.connect()

    execution_config = ExecutionConfigSchema()
    exchange = _build_exchange(app_config)
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=DynamicRiskValidator(),
        staleness_checker=StalenessChecker(execution_config),
        translator=DecisionTranslator(),
        monitor=OrderMonitor(exchange, execution_config.timeout_s),
        event_store=None,
    )

    if app_config.brain.openrouter_api_key:
        prompt_loader = PromptLoader()
        context_builder = ContextBuilder()
        factory = AgentFactory(app_config.brain, prompt_loader)
        scout = ScoutAgent(
            factory.create_scout_agent(), prompt_loader, context_builder
        )
        analyst = AnalystAgent(
            factory.create_analyst_agent(), prompt_loader, context_builder
        )
        trader = TraderAgent(
            factory.create_trader_agent(), prompt_loader, context_builder
        )
    else:
        logger.warning("KT_OPENROUTER_API_KEY not set; using noop agents")
        scout = _NoopScout()  # type: ignore[assignment]
        analyst = _NoopAnalyst()  # type: ignore[assignment]
        trader = _NoopTrader()  # type: ignore[assignment]

    router = AgentRouter(scout, analyst, trader)
    deps_provider = _NoopDepsProvider(_build_noop_dependencies())
    position_manager = PositionManager(
        break_even=BreakEvenMover(),
        trailing=TrailingStopChecker(),
        partial_exit=PartialExitChecker(),
        time_exit=TimeExitChecker(),
        scaling=ScaleInChecker(),
    )

    report_populator: TradeReportPopulator | None = None
    if app_config.reporting.enabled:
        await state_manager.connect()
        account = await state_manager.get_account_state()
        initial_balance = (
            account.total_balance_usdt
            if account is not None
            else Decimal("1000")
        )
        report_populator = TradeReportPopulator(
            report_dir=app_config.reporting.report_dir,
            initial_balance_usdt=initial_balance,
            max_action_entries=app_config.reporting.max_action_entries,
            max_trade_entries=app_config.reporting.max_trade_entries,
            refresh_interval_s=app_config.reporting.refresh_interval_s,
        )

    orchestrator = TradingOrchestrator(
        config=OrchestratorConfigSchema(),
        state_manager=state_manager,
        ingest_loop=DataIngestLoop(_NoopStreamManager()),
        order_flow_loop=OrderFlowLoop(_NoopOrderFlowFetcher(), interval_s=60),
        reasoning_loop=ReasoningLoop(
            symbols=app_config.trading.symbols,
            router=router,
            deps_provider=deps_provider,
            redis_client=redis_client,
            interval_s=5,
            report_populator=report_populator,
        ),
        execution_loop=ExecutionLoop(
            redis_client=redis_client,
            engine=engine,
            report_populator=report_populator,
        ),
        position_loop=PositionManagementLoop(
            manager=position_manager,
            state_manager=state_manager,
            atr_provider=_NoopAtrProvider(),
            interval_s=5,
            report_populator=report_populator,
        ),
        health_checker=HealthChecker(),
        report_populator=report_populator,
    )
    await orchestrator.start()


@trade.command()
@click.option("--dry-run", is_flag=True)
@click.pass_context
def start(ctx: click.Context, dry_run: bool) -> None:
    """Start the trading orchestrator."""
    app_config = ctx.obj["app_config"]
    if dry_run:
        click.echo("Dry run: orchestrator not started")
        return
    asyncio.run(_start_orchestrator(app_config))


@trade.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop the trading orchestrator."""
    _ = ctx
    click.echo("Stop requested. Use CTRL+C to terminate running process.")


@trade.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current trading system status."""
    app_config = ctx.obj["app_config"]
    state_manager = _build_state_manager(app_config)
    asyncio.run(state_manager.connect())
    positions = asyncio.run(state_manager.get_all_positions())
    orders = asyncio.run(state_manager.get_open_orders())
    click.echo(f"Positions: {len(positions)}")
    click.echo(f"Open orders: {len(orders)}")


@trade.command()
@click.pass_context
def positions(ctx: click.Context) -> None:
    """List open positions."""
    app_config = ctx.obj["app_config"]
    state_manager = _build_state_manager(app_config)
    asyncio.run(state_manager.connect())
    positions_list = asyncio.run(state_manager.get_all_positions())
    if not positions_list:
        click.echo("No open positions")
        return
    for position in positions_list:
        click.echo(
            f"{position.symbol} {position.side} qty={position.quantity} "
            f"entry={position.entry_price} sl={position.stop_loss} "
            f"tp={position.take_profit}",
        )


@trade.command()
@click.pass_context
def history(ctx: click.Context) -> None:
    """Show recent execution history from event store."""
    _ = ctx
    redis_client = RedisStateClient(RedisConfigSchema())
    asyncio.run(redis_client.connect())
    store = RedisEventStore(redis_client, EventStoreConfigSchema())
    events = asyncio.run(store.read("kt:events:positions", count=10))
    if not events:
        click.echo("No recent events")
        return
    for event in events:
        click.echo(f"{event.timestamp.isoformat()} {event.event_type}")
