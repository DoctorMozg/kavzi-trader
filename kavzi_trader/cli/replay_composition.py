import logging
from decimal import Decimal

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.brain.agent.analyst import AnalystAgent
from kavzi_trader.brain.agent.router import AgentRouter
from kavzi_trader.brain.agent.trader import TraderAgent
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.geometry.calculator import TradeGeometryCalculator
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.cli.runtime_services_schema import RuntimeServicesSchema
from kavzi_trader.cli.spine_composition import SpineComposer
from kavzi_trader.commons.sim_clock import SimClock
from kavzi_trader.config import AppConfig
from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.orchestrator.loops.decision_publisher import DecisionPublisher
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.llm_pipeline_plugin import LlmPipelinePlugin
from kavzi_trader.orchestrator.loops.reasoning_config import (
    ReasoningLoopConfigSchema,
)
from kavzi_trader.orchestrator.loops.strategy import StrategyLoop
from kavzi_trader.orchestrator.providers.live_dependencies_provider import (
    LiveDependenciesProvider,
)
from kavzi_trader.orchestrator.providers.live_order_flow_fetcher import (
    LiveOrderFlowFetcher,
)
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from kavzi_trader.paper.costs_schema import PaperCostsSchema
from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.paper.sim_market_feed import SimMarketFeed
from kavzi_trader.replay.historical_daily_closes import HistoricalDailyCloses
from kavzi_trader.replay.historical_order_flow_source import (
    HistoricalOrderFlowSource,
)
from kavzi_trader.replay.replay_data_schema import ReplayDataSchema
from kavzi_trader.replay.replay_needs_schema import ReplayNeedsSchema
from kavzi_trader.replay.replay_rig_schema import ReplayRigSchema
from kavzi_trader.replay.taped_agent_source import TapedAgentSource
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.scout import ScoutFilter
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.strategies.strategy_plugin import StrategyPlugin
from kavzi_trader.strategies.trend.trend_following_plugin import TrendFollowingPlugin
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore

logger = logging.getLogger(__name__)

REPLAY_STRATEGIES = ("trend_following", "llm_pipeline")
TREND_INTERVAL = "4h"


class ReplayComposer:
    """Builds the live spine and loops over a SimClock, SimMarketFeed and memory."""

    def __init__(
        self,
        app_config: AppConfig,
        precision: SymbolPrecision,
        costs: PaperCostsSchema,
        agents: TapedAgentSource | None = None,
    ) -> None:
        self._config = app_config
        self._precision = precision
        self._costs = costs
        self._agents = agents
        self._tier_registry = load_tier_registry()
        self._regime_policy = RegimePolicy(
            app_config.risk, app_config.scout.extreme_allowed_patterns
        )

    async def compose(
        self,
        strategy: str,
        data: ReplayDataSchema,
        start_ms: int,
    ) -> ReplayRigSchema:
        config = self._config
        symbols = list(data.candles)
        clock = SimClock(start_ms)
        feed = SimMarketFeed()
        balance = config.paper.initial_balance_usdt
        exchange = PaperExchangeClient(balance, self._costs, clock, feed)
        redis_client = RedisStateClient.in_memory()
        state = StateManager(redis_client, exchange, clock)
        exchange.set_account_store(state.account)
        await state.reset_for_paper(balance)
        await self._set_leverage(exchange, symbols)

        services = RuntimeServicesSchema.model_validate(
            {
                "exchange": exchange,
                "state_manager": state,
                "redis_client": redis_client,
                "event_store": RedisEventStore(redis_client, config.events),
                "ui_recorder": None,
            },
        )
        detector = VolatilityRegimeDetector(config.risk, self._regime_policy)
        spine = SpineComposer(config, self._tier_registry, detector, clock)
        engine = spine.create_engine(services, self._precision)
        state.set_protective_order_placer(engine.protective_orders)
        cache = MarketDataCache(
            symbols=symbols,
            indicator_calculator=TechnicalIndicatorCalculator(),
            max_candles=config.trading.history_candles,
        )
        order_flow = None
        if strategy == "llm_pipeline":
            plugin: StrategyPlugin = self._llm_plugin(
                LiveDependenciesProvider(
                    cache=cache,
                    confluence_calculator=ConfluenceCalculator(),
                    volatility_detector=detector,
                    state_manager=state,
                    timeframe=data.interval,
                    futures_config=config.futures,
                    tier_registry=self._tier_registry,
                ),
                spine,
                data,
                clock,
            )
            order_flow = LiveOrderFlowFetcher(
                HistoricalOrderFlowSource(clock, data.funding, data.metrics),
                cache,
                OrderFlowCalculator(KLINE_INTERVALS[data.interval] // 60, clock),
                symbols,
            )
        else:
            plugin = self._trend_plugin(strategy, data, redis_client)
        logger.info(
            "Replay rig: strategy=%s symbols=%s balance=%s costs=%s",
            strategy,
            symbols,
            balance,
            self._costs,
        )
        return ReplayRigSchema(
            clock=clock,
            feed=feed,
            exchange=exchange,
            market_cache=cache,
            event_store=services.event_store,
            redis_client=redis_client,
            strategy_loop=StrategyLoop(
                plugin, DecisionPublisher(redis_client), state, clock
            ),
            execution_loop=ExecutionLoop(redis_client, engine, state, clock=clock),
            position_loop=spine.create_position_loop(services, cache, self._precision),
            order_flow=order_flow,
            agents=self._agents if strategy == "llm_pipeline" else None,
            decision_stream=config.events.streams[AggregateType.DECISIONS],
            strategy=strategy,
            symbols=symbols,
        )

    async def _set_leverage(
        self, exchange: PaperExchangeClient, symbols: list[str]
    ) -> None:
        futures = self._config.futures
        for symbol in symbols:
            leverage = futures.symbol_leverage.get(symbol, futures.default_leverage)
            await exchange.futures_change_leverage(symbol, leverage)

    def _llm_plugin(
        self,
        deps_provider: LiveDependenciesProvider,
        spine: SpineComposer,
        data: ReplayDataSchema,
        clock: SimClock,
    ) -> LlmPipelinePlugin:
        if self._agents is None:
            msg = "the llm_pipeline replay needs an LLM agent source"
            raise ValueError(msg)
        prompts = PromptLoader()
        context = ContextBuilder()
        router = AgentRouter(
            ScoutFilter(self._config.scout, self._regime_policy),
            AnalystAgent(self._agents.create_analyst_agent(), prompts, context),
            TraderAgent(self._agents.create_trader_agent(), prompts, context),
            geometry_calculator=TradeGeometryCalculator(self._config.risk),
            analyst_concurrency_limit=self._config.brain.analyst_concurrency_limit,
        )
        # One tick per closed bar: live re-runs within a bar see the same
        # closed candles, and the idle ramp only saves wall time.
        return LlmPipelinePlugin(
            symbols=list(data.candles),
            router=router,
            deps_provider=deps_provider,
            interval_s=KLINE_INTERVALS[data.interval],
            filter_chain=spine.create_filter_chain(None),
            position_management=self._config.position_management,
            reasoning_config=ReasoningLoopConfigSchema(idle_ramp_stairs=()),
            clock=clock,
        )

    def _trend_plugin(
        self,
        strategy: str,
        data: ReplayDataSchema,
        redis_client: RedisStateClient,
    ) -> StrategyPlugin:
        if strategy == "trend_following" and data.daily_closes is not None:
            trend = self._config.strategy.trend_following.model_copy(
                update={"symbols": list(data.candles)},
            )
            return TrendFollowingPlugin(
                trend,
                HistoricalDailyCloses(data.daily_closes),
                TrendStateStore(redis_client),
            )
        msg = f"replay of {strategy!r} needs daily closes and the trend strategy"
        raise ValueError(msg)


def replay_needs(app_config: AppConfig, strategy: str) -> ReplayNeedsSchema:
    """The symbols, bar interval and extra series the strategy reads."""
    if strategy == "trend_following":
        return ReplayNeedsSchema(
            symbols=app_config.strategy.trend_following.symbols,
            interval=TREND_INTERVAL,
            daily_closes=True,
        )
    if strategy == "llm_pipeline":
        return ReplayNeedsSchema(
            symbols=app_config.trading.symbols,
            interval=app_config.trading.interval,
            metrics=True,
        )
    msg = f"replay supports {REPLAY_STRATEGIES}, got {strategy!r}"
    raise ValueError(msg)


def replay_costs(commission_rate: Decimal, slippage_bps: Decimal) -> PaperCostsSchema:
    """Taker fee from the paper config; maker stays at the Binance VIP0 default."""
    return PaperCostsSchema(taker_fee_rate=commission_rate, slippage_bps=slippage_bps)
