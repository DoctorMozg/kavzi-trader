import logging
from decimal import Decimal

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
from kavzi_trader.orchestrator.loops.strategy import StrategyLoop
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.paper.costs_schema import PaperCostsSchema
from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.paper.sim_market_feed import SimMarketFeed
from kavzi_trader.replay.historical_daily_closes import HistoricalDailyCloses
from kavzi_trader.replay.replay_data_schema import ReplayDataSchema
from kavzi_trader.replay.replay_rig_schema import ReplayRigSchema
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.strategies.strategy_plugin import StrategyPlugin
from kavzi_trader.strategies.trend.trend_following_plugin import TrendFollowingPlugin
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore

logger = logging.getLogger(__name__)

REPLAY_STRATEGIES = ("trend_following",)


class ReplayComposer:
    """Builds the live spine and loops over a SimClock, SimMarketFeed and memory."""

    def __init__(
        self,
        app_config: AppConfig,
        precision: SymbolPrecision,
        costs: PaperCostsSchema,
    ) -> None:
        self._config = app_config
        self._precision = precision
        self._costs = costs

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
        detector = VolatilityRegimeDetector(
            config.risk,
            RegimePolicy(config.risk, config.scout.extreme_allowed_patterns),
        )
        spine = SpineComposer(config, load_tier_registry(), detector, clock)
        engine = spine.create_engine(services, self._precision)
        state.set_protective_order_placer(engine.protective_orders)
        cache = MarketDataCache(
            symbols=symbols,
            indicator_calculator=TechnicalIndicatorCalculator(),
            max_candles=config.trading.history_candles,
        )
        plugin = self._plugin(strategy, data, redis_client)
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

    def _plugin(
        self,
        strategy: str,
        data: ReplayDataSchema,
        redis_client: RedisStateClient,
    ) -> StrategyPlugin:
        if strategy == "trend_following":
            trend = self._config.strategy.trend_following.model_copy(
                update={"symbols": list(data.candles)},
            )
            return TrendFollowingPlugin(
                trend,
                HistoricalDailyCloses(data.daily_closes),
                TrendStateStore(redis_client),
            )
        msg = f"replay supports {REPLAY_STRATEGIES}, got {strategy!r}"
        raise ValueError(msg)


def replay_costs(commission_rate: Decimal, slippage_bps: Decimal) -> PaperCostsSchema:
    """Taker fee from the paper config; maker stays at the Binance VIP0 default."""
    return PaperCostsSchema(taker_fee_rate=commission_rate, slippage_bps=slippage_bps)
