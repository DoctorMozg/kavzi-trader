import logging
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from kavzi_trader.brain.context.formatters import dump_json, dump_optional_json
from kavzi_trader.brain.context.market_snapshot import MarketSnapshotSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    ScoutDependenciesSchema,
    TradingDependenciesSchema,
)


logger = logging.getLogger(__name__)

MIN_CANDLES_EXPECTED = 5


class ContextBuilder(BaseModel):
    """
    Builds prompt context payloads from dependency schemas.
    """

    model_config = ConfigDict(frozen=True)

    def _warn_if_broken_data(
        self,
        symbol: str,
        deps: ScoutDependenciesSchema
        | AnalystDependenciesSchema
        | TradingDependenciesSchema,
    ) -> None:
        if deps.current_price == Decimal("0"):
            logger.warning(
                "Context for %s: current_price is 0, data may be broken",
                symbol,
            )
        if deps.indicators.atr_14 is None or deps.indicators.atr_14 == Decimal("0"):
            logger.warning("Context for %s: ATR is None/zero", symbol)
        if (
            deps.indicators.ema_20 is None
            and deps.indicators.ema_50 is None
            and deps.indicators.ema_200 is None
        ):
            logger.warning(
                "Context for %s: all EMA indicators are missing", symbol,
            )
        if len(deps.recent_candles) < MIN_CANDLES_EXPECTED:
            logger.warning(
                "Context for %s: only %d candles (expected >= %d)",
                symbol,
                len(deps.recent_candles),
                MIN_CANDLES_EXPECTED,
            )

    def build_scout_context(self, deps: ScoutDependenciesSchema) -> dict[str, str]:
        self._warn_if_broken_data(deps.symbol, deps)
        snapshot = MarketSnapshotSchema(
            symbol=deps.symbol,
            current_price=deps.current_price,
            timeframe=deps.timeframe,
            recent_candles=deps.recent_candles,
            indicators=deps.indicators,
            volatility_regime=deps.volatility_regime,
        )
        context = {"market_snapshot_json": dump_json(snapshot)}
        logger.debug(
            "Built scout context for %s: %d keys", deps.symbol, len(context),
        )
        return context

    def build_analyst_context(
        self,
        deps: AnalystDependenciesSchema,
    ) -> dict[str, str | None]:
        self._warn_if_broken_data(deps.symbol, deps)
        snapshot = MarketSnapshotSchema(
            symbol=deps.symbol,
            current_price=deps.current_price,
            timeframe=deps.timeframe,
            recent_candles=deps.recent_candles,
            indicators=deps.indicators,
            volatility_regime=deps.volatility_regime,
        )
        context: dict[str, str | None] = {
            "market_snapshot_json": dump_json(snapshot),
            "order_flow_json": dump_optional_json(deps.order_flow),
            "algorithm_confluence_json": dump_json(deps.algorithm_confluence),
        }
        logger.debug(
            "Built analyst context for %s: %d keys", deps.symbol, len(context),
        )
        return context

    def build_trader_context(
        self,
        deps: TradingDependenciesSchema,
    ) -> dict[str, str | None]:
        self._warn_if_broken_data(deps.symbol, deps)
        snapshot = MarketSnapshotSchema(
            symbol=deps.symbol,
            current_price=deps.current_price,
            timeframe=deps.timeframe,
            recent_candles=deps.recent_candles,
            indicators=deps.indicators,
            volatility_regime=deps.volatility_regime,
        )
        context: dict[str, str | None] = {
            "market_snapshot_json": dump_json(snapshot),
            "order_flow_json": dump_optional_json(deps.order_flow),
            "algorithm_confluence_json": dump_json(deps.algorithm_confluence),
            "account_state_json": dump_json(deps.account_state),
        }
        logger.debug(
            "Built trader context for %s: %d keys", deps.symbol, len(context),
        )
        return context
