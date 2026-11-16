import logging

from kavzi_trader.cli.runtime_services_schema import RuntimeServicesSchema
from kavzi_trader.config import AppConfig
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.orchestrator.providers.live_atr_provider import LiveAtrProvider
from kavzi_trader.orchestrator.providers.live_price_provider import LivePriceProvider
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.spine.execution.engine import ExecutionEngine
from kavzi_trader.spine.execution.event_recorder import ExecutionEventRecorder
from kavzi_trader.spine.execution.monitor import OrderMonitor
from kavzi_trader.spine.execution.precision_exchange import PrecisionExchangeClient
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.execution.translator import DecisionTranslator
from kavzi_trader.spine.filters.chain import PreTradeFilterChain
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.correlation import CorrelationFilter
from kavzi_trader.spine.filters.fear_greed_gate import FearGreedGateFilter
from kavzi_trader.spine.filters.funding import FundingRateFilter
from kavzi_trader.spine.filters.liquidity import LiquidityFilter
from kavzi_trader.spine.filters.movement import MinimumMovementFilter
from kavzi_trader.spine.filters.spike_cooldown import SpikeCooldownFilter
from kavzi_trader.spine.position.action_executor import PositionActionExecutor
from kavzi_trader.spine.position.exchange_fill_detector import ExchangeFillDetector
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.stall_exit import StallExitChecker
from kavzi_trader.spine.position.time_exit import TimeExitChecker
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.spine.risk.drawdown_circuit_breaker import DrawdownCircuitBreaker
from kavzi_trader.spine.risk.exposure import ExposureLimiter
from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from kavzi_trader.spine.risk.validator import DynamicRiskValidator
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector

logger = logging.getLogger(__name__)


class SpineComposer:
    """Builds the deterministic execution side: engine, filters, position loop."""

    def __init__(
        self,
        app_config: AppConfig,
        tier_registry: SymbolTierRegistry,
        volatility_detector: VolatilityRegimeDetector,
    ) -> None:
        self._config = app_config
        self._tier_registry = tier_registry
        self._volatility_detector = volatility_detector

    def create_engine(
        self,
        services: RuntimeServicesSchema,
        precision: SymbolPrecision,
    ) -> ExecutionEngine:
        logger.info("Creating execution engine")
        config = self._config
        liquidation_calculator = LiquidationCalculator(services.exchange)
        return ExecutionEngine(
            exchange=PrecisionExchangeClient(services.exchange, precision),
            state_manager=services.state_manager,
            risk_validator=DynamicRiskValidator(
                config.risk,
                self._tier_registry,
                liquidation_calculator,
                precision,
            ),
            staleness_checker=StalenessChecker(config.execution),
            translator=DecisionTranslator(),
            monitor=OrderMonitor(services.exchange, config.execution.timeout_s),
            event_store=services.event_store,
            leverage=config.futures.default_leverage,
            symbol_leverage=config.futures.symbol_leverage,
            close_recorder=services.ui_recorder,
            volatility_detector=self._volatility_detector,
            liquidation_calculator=liquidation_calculator,
            pullback_entry_expiry_ms=config.execution.pullback_entry_expiry_ms,
            precision=precision,
        )

    def create_filter_chain(
        self,
        fgi_gate: FearGreedGateFilter | None,
    ) -> PreTradeFilterChain:
        filters = self._config.filters
        return PreTradeFilterChain(
            volatility_detector=self._volatility_detector,
            funding_filter=FundingRateFilter(filters, self._tier_registry),
            movement_filter=MinimumMovementFilter(filters),
            exposure_limiter=ExposureLimiter(self._config.risk),
            liquidity_filter=LiquidityFilter(filters),
            correlation_filter=CorrelationFilter(filters),
            confluence_calculator=ConfluenceCalculator(),
            fear_greed_gate=fgi_gate,
            spike_cooldown_filter=SpikeCooldownFilter(filters),
            config=filters,
        )

    def create_position_loop(
        self,
        services: RuntimeServicesSchema,
        cache: MarketDataCache,
        precision: SymbolPrecision,
    ) -> PositionManagementLoop:
        orchestrator_config = self._config.orchestrator
        return PositionManagementLoop(
            manager=PositionManager(
                partial_exit=PartialExitChecker(precision),
                time_exit=TimeExitChecker(),
                stall_exit=StallExitChecker(),
                liquidation_emergency_percent=(
                    self._config.futures.liquidation_emergency_percent
                ),
            ),
            state_manager=services.state_manager,
            atr_provider=LiveAtrProvider(cache),
            price_provider=LivePriceProvider(cache),
            action_executor=PositionActionExecutor(
                exchange=PrecisionExchangeClient(services.exchange, precision),
                state_manager=services.state_manager,
            ),
            fill_detector=ExchangeFillDetector(
                exchange=services.exchange,
                state_manager=services.state_manager,
            ),
            interval_s=orchestrator_config.position_check_interval_s,
            ui_recorder=services.ui_recorder,
            cycle_timeout_s=orchestrator_config.position_cycle_timeout_s,
            drawdown_breaker=DrawdownCircuitBreaker(
                self._config.risk.drawdown_close_all_percent,
                services.state_manager,
                ExecutionEventRecorder(services.event_store),
            ),
        )
