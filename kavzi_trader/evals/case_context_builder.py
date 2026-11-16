import logging

from kavzi_trader.config import AppConfig
from kavzi_trader.domain.symbol_tier import SymbolTier
from kavzi_trader.evals.anonymized_case_schema import AnonymizedCaseSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.replay_kline_source import ReplayKlineSource
from kavzi_trader.evals.synthetic_account import EVAL_BALANCE_USDT, SyntheticAccount
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.orchestrator.futures_config import FuturesConfigSchema
from kavzi_trader.orchestrator.providers.live_dependencies_provider import (
    LiveDependenciesProvider,
)
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector

logger = logging.getLogger(__name__)


class CaseContextBuilder:
    """Builds the live LiveDependenciesProvider for one anonymized case.

    The market cache is filled through the same initialize() backfill the live
    bot runs at startup. Order flow and sentiment are absent, as when those
    live sources are unavailable.
    """

    def __init__(
        self,
        app_config: AppConfig,
        tier_registry: SymbolTierRegistry,
        volatility_detector: VolatilityRegimeDetector,
    ) -> None:
        self._config = app_config
        self._tiers = tier_registry
        self._volatility = volatility_detector

    async def build(
        self, case: EvalCaseSchema, anonymized: AnonymizedCaseSchema
    ) -> LiveDependenciesProvider:
        symbol = anonymized.symbol
        trading = self._config.trading
        cache = MarketDataCache(
            [symbol], TechnicalIndicatorCalculator(), trading.history_candles
        )
        await cache.initialize(ReplayKlineSource(anonymized.candles), case.interval)
        return LiveDependenciesProvider(
            cache=cache,
            confluence_calculator=ConfluenceCalculator(),
            volatility_detector=self._volatility,
            state_manager=SyntheticAccount(
                EVAL_BALANCE_USDT,
                anonymized.candles[-1].close_time,
            ),
            timeframe=case.interval,
            futures_config=self._futures_for(case.symbol, symbol),
            tier_registry=self._tier_view(case.symbol, symbol),
        )

    def _futures_for(self, real_symbol: str, alias: str) -> FuturesConfigSchema:
        futures = self._config.futures
        leverage = futures.symbol_leverage.get(real_symbol, futures.default_leverage)
        return futures.model_copy(
            update={"default_leverage": leverage, "symbol_leverage": {alias: leverage}}
        )

    def _tier_view(self, real_symbol: str, alias: str) -> SymbolTierRegistry:
        """The live registry's tiers, with the anonymous alias in the real tier."""
        return SymbolTierRegistry(
            tier_configs={t: self._tiers.get_config_for_tier(t) for t in SymbolTier},
            symbol_map={alias: self._tiers.get_tier(real_symbol)},
        )
