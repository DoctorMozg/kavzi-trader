import logging
from decimal import Decimal

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.binance.websocket.client import BinanceWebsocketClient
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.brain.agent.analyst import AnalystAgent
from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.agent.trader import TraderAgent
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.geometry.calculator import TradeGeometryCalculator
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.cli.runtime_services_schema import RuntimeServicesSchema
from kavzi_trader.cli.spine_composition import SpineComposer
from kavzi_trader.config import CONFIG_DIR, AppConfig
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.loop import ExternalSentimentLoop
from kavzi_trader.external.sources import build_enabled_sources
from kavzi_trader.external.synthesizer import SentimentSynthesizer
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.orchestrator.loops.decision_publisher import DecisionPublisher
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.ingest import DataIngestLoop
from kavzi_trader.orchestrator.loops.llm_pipeline_plugin import LlmPipelinePlugin
from kavzi_trader.orchestrator.loops.order_flow import OrderFlowLoop
from kavzi_trader.orchestrator.loops.strategy import StrategyLoop
from kavzi_trader.orchestrator.loops.ui_snapshot import UiSnapshotLoop
from kavzi_trader.orchestrator.orchestrator import TradingOrchestrator
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
from kavzi_trader.paper.state_initializer import PaperStateInitializer
from kavzi_trader.spine.filters.chain import PreTradeFilterChain
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.fear_greed_gate import FearGreedGateFilter
from kavzi_trader.spine.filters.scout import ScoutFilter
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.ui.recorder import UiEventRecorder
from kavzi_trader.ui.redis_publisher import RedisUiPublisher

logger = logging.getLogger(__name__)


def load_tier_registry() -> SymbolTierRegistry:
    return SymbolTierRegistry.from_yaml(CONFIG_DIR / "tiers.yaml")


def build_exchange(app_config: AppConfig) -> BinanceClient:
    return BinanceClient(
        api_key=app_config.api.binance.api_key.get_secret_value(),
        api_secret=app_config.api.binance.api_secret.get_secret_value(),
    )


def build_state_manager(
    app_config: AppConfig,
    exchange_client: ExchangeClient | None = None,
) -> StateManager:
    return StateManager(
        redis_config=app_config.redis,
        exchange_client=exchange_client or build_exchange(app_config),
    )


class OrchestratorComposer:
    """Wires the live or paper trading orchestrator, one subsystem per method."""

    def __init__(
        self,
        app_config: AppConfig,
        paper: bool = False,
        paper_balance: float | None = None,
    ) -> None:
        self._config = app_config
        self._is_paper = paper
        self._paper_balance = paper_balance
        self._tier_registry = load_tier_registry()
        self._regime_policy = RegimePolicy(
            app_config.risk,
            app_config.scout.extreme_allowed_patterns,
        )
        self._volatility_detector = VolatilityRegimeDetector(
            app_config.risk,
            self._regime_policy,
        )
        self._spine = SpineComposer(
            app_config,
            self._tier_registry,
            self._volatility_detector,
        )

    async def compose(self) -> TradingOrchestrator:
        config = self._config
        mode = "PAPER mode " if self._is_paper else ""
        logger.info(
            "Starting orchestrator in %sfor symbols=%s interval=%s",
            mode,
            config.trading.symbols,
            config.trading.interval,
        )
        if self._is_paper:
            config.validate_for_paper_trading()
        else:
            config.validate_for_trading()

        exchange = self._create_exchange()
        await self._init_futures(exchange)
        services = await self._create_services(exchange)
        cache = await self._create_market_data_cache(exchange)

        ws_client = self._create_ws_client()
        stream_manager = LiveStreamManager(
            ws_client=ws_client,
            cache=cache,
            symbols=config.trading.symbols,
            interval=config.trading.interval,
        )
        ws_client.set_on_error(stream_manager.handle_ws_error)

        prompt_loader = PromptLoader()
        factory = AgentFactory(
            config.brain,
            prompt_loader,
            risk_config=config.risk,
            tier_registry=self._tier_registry,
        )
        external_cache = self._create_external_cache()
        external_loop = self._create_external_loop(
            external_cache, factory, prompt_loader
        )
        fgi_gate = (
            FearGreedGateFilter(external_cache, config.filters)
            if external_cache is not None
            else None
        )
        deps_provider = LiveDependenciesProvider(
            cache=cache,
            confluence_calculator=ConfluenceCalculator(),
            volatility_detector=self._volatility_detector,
            state_manager=services.state_manager,
            timeframe=config.trading.interval,
            futures_config=config.futures,
            external_cache=external_cache,
            tier_registry=self._tier_registry,
        )
        router = self._create_router(factory, prompt_loader, fgi_gate)
        engine = self._spine.create_engine(services)
        services.state_manager.set_protective_order_placer(engine.protective_orders)

        logger.info("Assembling orchestrator with all loops")
        return TradingOrchestrator(
            config=config.orchestrator,
            state_manager=services.state_manager,
            ingest_loop=DataIngestLoop(stream_manager),
            order_flow_loop=self._create_order_flow_loop(exchange, cache),
            reasoning_loop=self._create_reasoning_loop(
                services,
                router,
                deps_provider,
                self._spine.create_filter_chain(fgi_gate),
            ),
            execution_loop=ExecutionLoop(
                redis_client=services.redis_client,
                engine=engine,
                state_manager=services.state_manager,
                ui_recorder=services.ui_recorder,
            ),
            position_loop=self._spine.create_position_loop(services, cache),
            ui_snapshot_loop=(
                UiSnapshotLoop(
                    recorder=services.ui_recorder,
                    state_manager=services.state_manager,
                    market_data=cache,
                    symbols=config.trading.symbols,
                    config=config.ui,
                )
                if services.ui_recorder is not None
                else None
            ),
            is_paper=self._is_paper,
            external_sentiment_loop=external_loop,
            shutdown_hooks={
                "websocket": ws_client.stop,
                "exchange": exchange.close,
                "redis": services.redis_client.close,
            },
        )

    def _paper_balance_usdt(self) -> Decimal:
        if self._paper_balance is not None:
            return Decimal(str(self._paper_balance))
        return self._config.paper.initial_balance_usdt

    def _create_exchange(self) -> ExchangeClient:
        if not self._is_paper:
            return build_exchange(self._config)
        balance = self._paper_balance_usdt()
        exchange = PaperExchangeClient(
            initial_balance_usdt=balance,
            commission_rate=self._config.paper.commission_rate,
        )
        logger.info("Paper exchange created: balance=%s USDT", balance)
        return exchange

    async def _init_futures(self, exchange: ExchangeClient) -> None:
        futures = self._config.futures
        logger.info("Initialising futures leverage and margin type")
        for symbol in self._config.trading.symbols:
            leverage = futures.symbol_leverage.get(symbol, futures.default_leverage)
            await exchange.futures_change_leverage(symbol, leverage)
            await exchange.futures_change_margin_type(symbol, futures.margin_type)
        logger.info(
            "Futures initialised: default_leverage=%sx margin_type=%s",
            futures.default_leverage,
            futures.margin_type,
        )

    async def _create_services(self, exchange: ExchangeClient) -> RuntimeServicesSchema:
        logger.info("Building state manager and exchange client")
        state_manager = build_state_manager(self._config, exchange)

        logger.info("Connecting to Redis")
        redis_client = RedisStateClient(self._config.redis)
        await redis_client.connect()

        if isinstance(exchange, PaperExchangeClient):
            await state_manager.connect()
            await PaperStateInitializer().initialize(
                exchange,
                state_manager,
                balance_usdt=self._paper_balance_usdt(),
                reset_on_start=self._config.paper.reset_on_start,
            )

        ui_recorder = await self._create_ui_recorder(state_manager, redis_client)
        return RuntimeServicesSchema.model_validate(
            {
                "exchange": exchange,
                "state_manager": state_manager,
                "redis_client": redis_client,
                "event_store": RedisEventStore(redis_client, self._config.events),
                "ui_recorder": ui_recorder,
            },
        )

    async def _create_ui_recorder(
        self,
        state_manager: StateManager,
        redis_client: RedisStateClient,
    ) -> UiEventRecorder | None:
        if not self._config.ui.enabled:
            return None
        await state_manager.connect()
        account = await state_manager.get_account_state()
        initial_balance = (
            account.total_balance_usdt if account is not None else Decimal(1000)
        )
        logger.info(
            "Publishing dashboard events, initial_balance=%s USDT",
            initial_balance,
        )
        return UiEventRecorder(
            RedisUiPublisher(redis_client.client, self._config.ui),
            initial_balance_usdt=initial_balance,
            is_paper=self._is_paper,
        )

    async def _create_market_data_cache(
        self, exchange: ExchangeClient
    ) -> MarketDataCache:
        trading = self._config.trading
        logger.info(
            "Initialising market data cache for %d symbols (REST backfill)",
            len(trading.symbols),
        )
        cache = MarketDataCache(
            symbols=trading.symbols,
            indicator_calculator=TechnicalIndicatorCalculator(),
            max_candles=trading.history_candles,
        )
        await cache.initialize(exchange, trading.interval)
        logger.info("Market data cache initialised")
        return cache

    def _create_ws_client(self) -> BinanceWebsocketClient:
        logger.info("Creating WebSocket client and stream manager")
        if self._is_paper:
            return BinanceWebsocketClient(api_key=None, api_secret=None)
        binance = self._config.api.binance
        return BinanceWebsocketClient(
            api_key=binance.api_key.get_secret_value(),
            api_secret=binance.api_secret.get_secret_value(),
        )

    def _create_order_flow_loop(
        self,
        exchange: ExchangeClient,
        cache: MarketDataCache,
    ) -> OrderFlowLoop:
        fetcher = LiveOrderFlowFetcher(
            exchange=exchange,
            cache=cache,
            calculator=OrderFlowCalculator(
                interval_minutes=KLINE_INTERVALS[self._config.trading.interval] // 60,
            ),
            symbols=self._config.trading.symbols,
        )
        return OrderFlowLoop(
            fetcher,
            interval_s=self._config.orchestrator.order_flow_fetch_interval_s,
        )

    def _create_external_cache(self) -> ExternalDataCache | None:
        if not self._config.external_sources.enabled:
            return None
        return ExternalDataCache()

    def _create_external_loop(
        self,
        external_cache: ExternalDataCache | None,
        factory: AgentFactory,
        prompt_loader: PromptLoader,
    ) -> ExternalSentimentLoop | None:
        external = self._config.external_sources
        if external_cache is None:
            return None
        sources = build_enabled_sources(external)
        if not sources:
            return None
        synthesizer = None
        synth_key = self._config.brain.api_key_for(external.synthesizer.provider)
        if external.synthesizer.enabled and synth_key.get_secret_value():
            synthesizer = SentimentSynthesizer(
                factory.create_synthesizer_agent(external.synthesizer),
                prompt_loader,
            )
        logger.info("External sources enabled: %s", [s.name for s in sources])
        return ExternalSentimentLoop(
            sources=sources,
            synthesizer=synthesizer,
            cache=external_cache,
            interval_s=external.run_interval_s,
            circuit_breaker_config=external.circuit_breaker,
        )

    def _create_router(
        self,
        factory: AgentFactory,
        prompt_loader: PromptLoader,
        fgi_gate: FearGreedGateFilter | None,
    ) -> AgentRouter:
        logger.info(
            "Creating brain agents (Analyst via %s, Trader via %s); "
            "Scout is algorithmic",
            self._config.brain.analyst.provider,
            self._config.brain.trader.provider,
        )
        context_builder = ContextBuilder()
        router = AgentRouter(
            ScoutFilter(self._config.scout, self._regime_policy),
            AnalystAgent(
                factory.create_analyst_agent(), prompt_loader, context_builder
            ),
            TraderAgent(factory.create_trader_agent(), prompt_loader, context_builder),
            geometry_calculator=TradeGeometryCalculator(self._config.risk),
            confluence_override=fgi_gate,
            analyst_concurrency_limit=self._config.brain.analyst_concurrency_limit,
        )
        logger.info("Brain agents created")
        return router

    def _create_reasoning_loop(
        self,
        services: RuntimeServicesSchema,
        router: AgentRouter,
        deps_provider: LiveDependenciesProvider,
        filter_chain: PreTradeFilterChain,
    ) -> StrategyLoop:
        plugin = LlmPipelinePlugin(
            symbols=self._config.trading.symbols,
            router=router,
            deps_provider=deps_provider,
            interval_s=self._config.orchestrator.reasoning_interval_s,
            ui_recorder=services.ui_recorder,
            filter_chain=filter_chain,
            position_management=self._config.position_management,
        )
        return StrategyLoop(
            plugin=plugin,
            publisher=DecisionPublisher(services.redis_client),
            state_manager=services.state_manager,
        )
