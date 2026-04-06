"""
Trading commands for the KavziTrader CLI.
"""

import asyncio
import logging
from decimal import Decimal
from pathlib import Path

import click
import httpx
from openai import AsyncOpenAI

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.websocket.client import BinanceWebsocketClient
from kavzi_trader.brain.agent.analyst import AnalystAgent
from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.agent.trader import TraderAgent
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.dependencies import rebuild_deferred_models
from kavzi_trader.config import AppConfig
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.loop import ExternalSentimentLoop
from kavzi_trader.external.sources import build_enabled_sources
from kavzi_trader.external.synthesizer import SentimentSynthesizer
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
from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.filters.chain import PreTradeFilterChain
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.correlation import CorrelationFilter
from kavzi_trader.spine.filters.fear_greed_gate import FearGreedGateFilter
from kavzi_trader.spine.filters.funding import FundingRateFilter
from kavzi_trader.spine.filters.liquidity import LiquidityFilter
from kavzi_trader.spine.filters.movement import MinimumMovementFilter
from kavzi_trader.spine.filters.scout import ScoutFilter
from kavzi_trader.spine.filters.spike_cooldown import SpikeCooldownFilter
from kavzi_trader.spine.position.action_executor import PositionActionExecutor
from kavzi_trader.spine.position.break_even import BreakEvenMover
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.time_exit import TimeExitChecker
from kavzi_trader.spine.position.trailing import TrailingStopChecker
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.redis_client import RedisStateClient

logger = logging.getLogger(__name__)


@click.group()
def trade() -> None:
    """Trading commands."""


def _build_state_manager(
    app_config: AppConfig,
    exchange_client: BinanceClient | None = None,
) -> StateManager:
    client = exchange_client or _build_exchange(app_config)
    return StateManager(
        redis_config=app_config.redis,
        exchange_client=client,
    )


def _build_exchange(app_config: AppConfig) -> BinanceClient:
    return BinanceClient(
        api_key=app_config.api.binance.api_key,
        api_secret=app_config.api.binance.api_secret,
    )


async def _start_orchestrator(
    app_config: AppConfig,
    paper: bool = False,
    paper_balance: float | None = None,
) -> None:
    is_paper = paper
    if is_paper:
        logger.info(
            "Starting orchestrator in PAPER mode for symbols=%s interval=%s",
            app_config.trading.symbols,
            app_config.trading.interval,
        )
        app_config.validate_for_paper_trading()
    else:
        logger.info(
            "Starting orchestrator for symbols=%s interval=%s",
            app_config.trading.symbols,
            app_config.trading.interval,
        )
        app_config.validate_for_trading()
    rebuild_deferred_models()

    # --- Symbol tier registry ---
    tier_registry = SymbolTierRegistry.from_yaml(Path("config/tiers.yaml"))

    # --- Exchange client ---
    exchange: BinanceClient
    if is_paper:
        balance = (
            Decimal(str(paper_balance))
            if paper_balance is not None
            else app_config.paper.initial_balance_usdt
        )
        exchange = PaperExchangeClient(
            initial_balance_usdt=balance,
            commission_rate=app_config.paper.commission_rate,
        )
        logger.info("Paper exchange created: balance=%s USDT", balance)
    else:
        exchange = _build_exchange(app_config)

    # --- Futures initialization ---
    logger.info("Initialising futures leverage and margin type")
    for symbol in app_config.trading.symbols:
        leverage = app_config.futures.symbol_leverage.get(
            symbol,
            app_config.futures.default_leverage,
        )
        await exchange.futures_change_leverage(symbol, leverage)
        await exchange.futures_change_margin_type(
            symbol,
            app_config.futures.margin_type,
        )
    logger.info(
        "Futures initialised: default_leverage=%sx margin_type=%s",
        app_config.futures.default_leverage,
        app_config.futures.margin_type,
    )

    logger.info("Building state manager and exchange client")
    state_manager = _build_state_manager(app_config, exchange)

    logger.info("Connecting to Redis")
    redis_client = RedisStateClient(app_config.redis)
    await redis_client.connect()

    # --- Reset paper state and seed fresh balance ---
    if is_paper and isinstance(exchange, PaperExchangeClient):
        await state_manager.connect()
        await state_manager.reset_for_paper(balance)
        exchange.set_account_store(state_manager.account)
        logger.info("Paper state reset in Redis: %s USDT", balance)

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
        api_key=app_config.api.binance.api_key if not is_paper else None,
        api_secret=app_config.api.binance.api_secret if not is_paper else None,
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
    # --- Brain prompt loader (needed by synthesizer and agents) ---
    prompt_loader = PromptLoader()

    # --- External data sources ---
    external_cache: ExternalDataCache | None = None
    external_sentiment_loop: ExternalSentimentLoop | None = None
    if app_config.external_sources.enabled:
        external_cache = ExternalDataCache()
        ext_sources = build_enabled_sources(app_config.external_sources)
        synth_config = app_config.external_sources.synthesizer
        synthesizer = None
        if synth_config.enabled and app_config.brain.openrouter_api_key:
            from pydantic_ai import Agent
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            from kavzi_trader.external.synthesizer import _SynthesizerOutputSchema

            synth_provider = OpenAIProvider(
                openai_client=AsyncOpenAI(
                    base_url=app_config.brain.openrouter_base_url,
                    api_key=app_config.brain.openrouter_api_key,
                    timeout=httpx.Timeout(30.0, connect=10.0),
                    default_headers={
                        "HTTP-Referer": "https://github.com/kavzitrader",
                        "X-Title": "KavziTrader-Synthesizer",
                    },
                ),
            )
            synth_model = OpenAIChatModel(
                synth_config.model_id,
                provider=synth_provider,
            )
            synth_system_prompt = prompt_loader.render_system_prompt("synthesizer")
            from pydantic_ai.settings import ModelSettings

            synth_settings = ModelSettings(
                temperature=synth_config.temperature,
                seed=synth_config.seed,
            )
            synth_agent: Agent[None, _SynthesizerOutputSchema] = Agent(
                synth_model,
                output_type=_SynthesizerOutputSchema,
                instructions=synth_system_prompt,
                retries=synth_config.retries,
                model_settings=synth_settings,
            )
            synthesizer = SentimentSynthesizer(synth_agent, prompt_loader)
            logger.info(
                "Sentiment Synthesizer created with model %s",
                synth_config.model_id,
            )
        if ext_sources:
            external_sentiment_loop = ExternalSentimentLoop(
                sources=ext_sources,
                synthesizer=synthesizer,
                cache=external_cache,
                interval_s=app_config.external_sources.run_interval_s,
                circuit_breaker_config=app_config.external_sources.circuit_breaker,
            )
            logger.info(
                "External sources enabled: %s",
                [s.name for s in ext_sources],
            )

    deps_provider = LiveDependenciesProvider(
        cache=cache,
        confluence_calculator=ConfluenceCalculator(),
        volatility_detector=VolatilityRegimeDetector(),
        state_manager=state_manager,
        exchange=exchange,
        event_store=event_store,
        timeframe=app_config.trading.interval,
        futures_config=app_config.futures,
        external_cache=external_cache,
        tier_registry=tier_registry,
    )
    atr_provider = LiveAtrProvider(cache)

    # --- Brain agents ---
    logger.info(
        "Creating brain agents (Analyst/Trader) via OpenRouter; Scout is algorithmic",
    )
    context_builder = ContextBuilder()
    factory = AgentFactory(app_config.brain, prompt_loader)
    scout = ScoutFilter(app_config.scout)
    analyst = AnalystAgent(
        factory.create_analyst_agent(),
        prompt_loader,
        context_builder,
    )
    trader = TraderAgent(
        factory.create_trader_agent(),
        prompt_loader,
        context_builder,
    )

    router = AgentRouter(scout, analyst, trader)
    logger.info("Brain agents created")

    position_manager = PositionManager(
        break_even=BreakEvenMover(),
        trailing=TrailingStopChecker(),
        partial_exit=PartialExitChecker(),
        time_exit=TimeExitChecker(),
    )

    # --- Reporting ---
    report_populator: TradeReportPopulator | None = None
    if app_config.reporting.enabled:
        logger.info("Initialising trade report populator")
        try:
            await state_manager.connect()
            account = await state_manager.get_account_state()
            initial_balance = (
                account.total_balance_usdt if account is not None else Decimal(1000)
            )
            report_populator = TradeReportPopulator(
                report_dir=app_config.reporting.report_dir,
                initial_balance_usdt=initial_balance,
                max_action_entries=app_config.reporting.max_action_entries,
                max_trade_entries=app_config.reporting.max_trade_entries,
                max_closed_position_entries=app_config.reporting.max_closed_position_entries,
                refresh_interval_s=app_config.reporting.refresh_interval_s,
            )
            logger.info(
                "Report populator ready, initial_balance=%s USDT",
                initial_balance,
            )
        except Exception:
            logger.exception(
                "Failed to initialize report populator, continuing without reporting",
            )

    # --- Execution engine ---
    logger.info("Creating execution engine")
    engine = ExecutionEngine(
        exchange=exchange,
        state_manager=state_manager,
        risk_validator=DynamicRiskValidator(app_config.risk, tier_registry),
        staleness_checker=StalenessChecker(app_config.execution),
        translator=DecisionTranslator(),
        monitor=OrderMonitor(exchange, app_config.execution.timeout_s),
        event_store=event_store,
        leverage=app_config.futures.default_leverage,
        report_populator=report_populator,
    )

    # --- Pre-trade filter chain ---
    fgi_gate: FearGreedGateFilter | None = None
    if external_cache is not None:
        fgi_gate = FearGreedGateFilter(external_cache, app_config.filters)
    filter_chain = PreTradeFilterChain(
        volatility_detector=VolatilityRegimeDetector(),
        funding_filter=FundingRateFilter(app_config.filters, tier_registry),
        movement_filter=MinimumMovementFilter(app_config.filters),
        exposure_limiter=ExposureLimiter(app_config.risk),
        liquidity_filter=LiquidityFilter(app_config.filters),
        correlation_filter=CorrelationFilter(app_config.filters),
        confluence_calculator=ConfluenceCalculator(),
        fear_greed_gate=fgi_gate,
        spike_cooldown_filter=SpikeCooldownFilter(app_config.filters),
        config=app_config.filters,
    )

    # --- Orchestrator ---
    logger.info("Assembling orchestrator with all loops")
    orchestrator = TradingOrchestrator(
        config=app_config.orchestrator,
        state_manager=state_manager,
        price_provider=cache,
        trading_symbols=app_config.trading.symbols,
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
            state_manager=state_manager,
            filter_chain=filter_chain,
        ),
        execution_loop=ExecutionLoop(
            redis_client=redis_client,
            engine=engine,
            state_manager=state_manager,
            report_populator=report_populator,
        ),
        position_loop=PositionManagementLoop(
            manager=position_manager,
            state_manager=state_manager,
            atr_provider=atr_provider,
            action_executor=PositionActionExecutor(
                exchange=exchange,
                state_manager=state_manager,
            ),
            interval_s=app_config.orchestrator.position_check_interval_s,
            report_populator=report_populator,
        ),
        health_checker=HealthChecker(),
        report_populator=report_populator,
        is_paper=is_paper,
        external_sentiment_loop=external_sentiment_loop,
    )
    await orchestrator.start()


@trade.command()
@click.option("--dry-run", is_flag=True)
@click.option(
    "--paper",
    is_flag=True,
    help="Paper trading mode with simulated orders and live market data.",
)
@click.option(
    "--paper-balance",
    type=float,
    default=None,
    help="Initial paper balance in USDT (default: from config or 10000).",
)
@click.pass_context
def start(
    ctx: click.Context,
    dry_run: bool,
    paper: bool,
    paper_balance: float | None,
) -> None:
    """Start the trading orchestrator."""
    app_config = ctx.obj["app_config"]
    if dry_run:
        click.echo("Dry run: orchestrator not started")
        return
    if paper:
        balance_display = (
            paper_balance
            if paper_balance is not None
            else app_config.paper.initial_balance_usdt
        )
        click.echo("=" * 60)
        click.echo("  PAPER FUTURES TRADING MODE")
        click.echo(f"  Initial balance: {balance_display} USDT")
        click.echo(f"  Default leverage: {app_config.futures.default_leverage}x")
        click.echo(f"  Margin type: {app_config.futures.margin_type}")
        click.echo(f"  Commission rate: {app_config.paper.commission_rate}")
        click.echo(
            "  Orders are simulated. Market data is LIVE.",
        )
        click.echo("=" * 60)
    asyncio.run(
        _start_orchestrator(
            app_config,
            paper=paper,
            paper_balance=paper_balance,
        ),
    )


@trade.command()
def stop() -> None:
    """Stop the trading orchestrator."""
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
