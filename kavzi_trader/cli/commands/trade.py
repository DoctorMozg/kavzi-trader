"""
Trading commands for the KavziTrader CLI.
"""

import asyncio
import logging
from decimal import Decimal

import click

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.websocket.client import BinanceWebsocketClient
from kavzi_trader.brain.agent.analyst import AnalystAgent
from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.agent.scout import ScoutAgent
from kavzi_trader.brain.agent.trader import TraderAgent
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.dependencies import rebuild_deferred_models
from kavzi_trader.config import AppConfig
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.orchestrator.health import HealthChecker
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.loops.order_flow import OrderFlowLoop
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.orchestrator.loops.reasoning import ReasoningLoop
from kavzi_trader.orchestrator.orchestrator import TradingOrchestrator
from kavzi_trader.orchestrator.providers.live_atr_provider import LiveAtrProvider
from kavzi_trader.orchestrator.providers.live_dependencies_provider import (
    LiveDependenciesProvider,
)
from kavzi_trader.orchestrator.providers.live_order_flow_fetcher import (
    LiveOrderFlowFetcher,
)
from kavzi_trader.orchestrator.providers.live_stream_manager import LiveStreamManager
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.position.break_even import BreakEvenMover
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.scaling import ScaleInChecker
from kavzi_trader.spine.position.time_exit import TimeExitChecker
from kavzi_trader.spine.position.trailing import TrailingStopChecker
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.redis_client import RedisStateClient

logger = logging.getLogger(__name__)


@click.group()
def trade() -> None:
    """Trading commands."""


def _build_state_manager(app_config: AppConfig) -> StateManager:
    return StateManager(
        redis_config=app_config.redis,
        exchange_client=_build_exchange(app_config),
    )


def _build_exchange(app_config: AppConfig) -> BinanceClient:
    return BinanceClient(
        api_key=app_config.api.binance.api_key,
        api_secret=app_config.api.binance.api_secret,
        testnet=app_config.api.binance.testnet,
    )


async def _start_orchestrator(app_config: AppConfig) -> None:
    logger.info(
        "Starting orchestrator for symbols=%s interval=%s testnet=%s",
        app_config.trading.symbols,
        app_config.trading.interval,
        app_config.api.binance.testnet,
    )
    app_config.validate_for_trading()
    rebuild_deferred_models()

    logger.info("Building state manager and exchange client")
    state_manager = _build_state_manager(app_config)
    exchange = _build_exchange(app_config)

    logger.info("Connecting to Redis")
    redis_client = RedisStateClient(app_config.redis)
    await redis_client.connect()

    event_store = RedisEventStore(redis_client, app_config.events)

    # --- Market data cache (REST backfill) ---
    logger.info(
        "Initialising market data cache for %d symbols (REST backfill)",
        len(app_config.trading.symbols),
    )
    cache = MarketDataCache(
        symbols=app_config.trading.symbols,
        indicator_calculator=TechnicalIndicatorCalculator(),
        max_candles=app_config.trading.history_candles,
    )
    await cache.initialize(exchange, app_config.trading.interval)
    logger.info("Market data cache initialised")

    # --- Real providers ---
    logger.info("Creating WebSocket client and stream manager")
    ws_client = BinanceWebsocketClient(
        api_key=app_config.api.binance.api_key,
        api_secret=app_config.api.binance.api_secret,
        testnet=app_config.api.binance.testnet,
    )
    stream_manager = LiveStreamManager(
        ws_client=ws_client,
        cache=cache,
        symbols=app_config.trading.symbols,
        interval=app_config.trading.interval,
    )
    order_flow_fetcher = LiveOrderFlowFetcher(
        exchange=exchange,
        cache=cache,
        calculator=OrderFlowCalculator(),
        symbols=app_config.trading.symbols,
    )
    deps_provider = LiveDependenciesProvider(
        cache=cache,
        confluence_calculator=ConfluenceCalculator(),
        volatility_detector=VolatilityRegimeDetector(),
        state_manager=state_manager,
        exchange=exchange,
        event_store=event_store,
        timeframe=app_config.trading.interval,
    )
    atr_provider = LiveAtrProvider(cache)

    # --- Execution engine ---
    logger.info("Creating execution engine")
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=DynamicRiskValidator(),
        staleness_checker=StalenessChecker(app_config.execution),
        translator=DecisionTranslator(),
        monitor=OrderMonitor(exchange, app_config.execution.timeout_s),
        event_store=event_store,
    )

    # --- Brain agents ---
    logger.info(
        "Creating brain agents (Scout/Analyst/Trader) via OpenRouter",
    )
    prompt_loader = PromptLoader()
    context_builder = ContextBuilder()
    factory = AgentFactory(app_config.brain, prompt_loader)
    scout = ScoutAgent(
        factory.create_scout_agent(), prompt_loader, context_builder,
    )
    analyst = AnalystAgent(
        factory.create_analyst_agent(), prompt_loader, context_builder,
    )
    trader = TraderAgent(
        factory.create_trader_agent(), prompt_loader, context_builder,
    )

    router = AgentRouter(scout, analyst, trader)
    logger.info("Brain agents created")

    position_manager = PositionManager(
        break_even=BreakEvenMover(),
        trailing=TrailingStopChecker(),
        partial_exit=PartialExitChecker(),
        time_exit=TimeExitChecker(),
        scaling=ScaleInChecker(),
    )

    # --- Reporting ---
    report_populator: TradeReportPopulator | None = None
    if app_config.reporting.enabled:
        logger.info("Initialising trade report populator")
        try:
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
            logger.info(
                "Report populator ready, initial_balance=%s USDT",
                initial_balance,
            )
        except Exception:
            logger.exception(
                "Failed to initialize report populator,"
                " continuing without reporting",
            )

    # --- Orchestrator ---
    logger.info("Assembling orchestrator with all loops")
    orchestrator = TradingOrchestrator(
        config=app_config.orchestrator,
        state_manager=state_manager,
        ingest_loop=DataIngestLoop(stream_manager),
        order_flow_loop=OrderFlowLoop(
            order_flow_fetcher,
            interval_s=app_config.orchestrator.order_flow_fetch_interval_s,
        ),
        reasoning_loop=ReasoningLoop(
            symbols=app_config.trading.symbols,
            router=router,
            deps_provider=deps_provider,
            redis_client=redis_client,
            interval_s=app_config.orchestrator.reasoning_interval_s,
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
            atr_provider=atr_provider,
            interval_s=app_config.orchestrator.position_check_interval_s,
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
    app_config = ctx.obj["app_config"]
    redis_client = RedisStateClient(app_config.redis)
    asyncio.run(redis_client.connect())
    store = RedisEventStore(redis_client, app_config.events)
    events = asyncio.run(store.read("kt:events:positions", count=10))
    if not events:
        click.echo("No recent events")
        return
    for event in events:
        click.echo(f"{event.timestamp.isoformat()} {event.event_type}")
