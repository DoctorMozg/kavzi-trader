import logging
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from kavzi_trader.brain.context.formatters import (
    format_candles_table,
    format_indicators_compact,
    format_order_flow_compact,
)
from kavzi_trader.brain.context.market_snapshot import MarketSnapshotSchema
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
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
        deps: AnalystDependenciesSchema | TradingDependenciesSchema,
    ) -> None:
        if deps.current_price == Decimal(0):
            logger.warning(
                "Context for %s: current_price is 0, data may be broken",
                symbol,
            )
        if deps.indicators.atr_14 is None or deps.indicators.atr_14 == Decimal(0):
            logger.warning("Context for %s: ATR is None/zero", symbol)
        if (
            deps.indicators.ema_20 is None
            and deps.indicators.ema_50 is None
            and deps.indicators.ema_200 is None
        ):
            logger.warning(
                "Context for %s: all EMA indicators are missing",
                symbol,
            )
        if len(deps.recent_candles) < MIN_CANDLES_EXPECTED:
            logger.warning(
                "Context for %s: only %d candles (expected >= %d)",
                symbol,
                len(deps.recent_candles),
                MIN_CANDLES_EXPECTED,
            )

    def _build_market_context(
        self,
        deps: AnalystDependenciesSchema | TradingDependenciesSchema,
    ) -> dict[str, Any]:
        snapshot = MarketSnapshotSchema(
            symbol=deps.symbol,
            current_price=deps.current_price,
            timeframe=deps.timeframe,
            recent_candles=deps.recent_candles,
            indicators=deps.indicators,
            volatility_regime=deps.volatility_regime,
        )
        return {
            "market_snapshot": snapshot.model_dump(),
            "candles_table": format_candles_table(deps.recent_candles),
            "indicators_compact": format_indicators_compact(deps.indicators),
        }

    def build_analyst_context(
        self,
        deps: AnalystDependenciesSchema,
    ) -> dict[str, Any]:
        self._warn_if_broken_data(deps.symbol, deps)
        context = self._build_market_context(deps)
        dual = deps.algorithm_confluence
        context.update(
            {
                "order_flow_compact": format_order_flow_compact(deps.order_flow),
                "algorithm_confluence_long": dual.long.model_dump(),
                "algorithm_confluence_short": dual.short.model_dump(),
                "detected_side": dual.detected_side,
                "futures_leverage": deps.leverage,
            }
        )
        logger.debug(
            "Built analyst context for %s: %d keys",
            deps.symbol,
            len(context),
        )
        return context

    def build_trader_context(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
    ) -> dict[str, Any]:
        self._warn_if_broken_data(deps.symbol, deps)
        context = self._build_market_context(deps)
        positions_text = (
            "No open positions."
            if not deps.open_positions
            else "\n".join(
                f"- {p.symbol} {p.side} {p.quantity} @ {p.entry_price}"
                f" | SL: {p.current_stop_loss} | TP: {p.take_profit}"
                f" | Liq: {p.liquidation_price}"
                f" | uPnL: {p.unrealized_pnl}"
                for p in deps.open_positions
            )
        )
        funding_24h: str | None = None
        if deps.order_flow and deps.order_flow.funding_rate:
            rate_24h = abs(deps.order_flow.funding_rate) * 3
            funding_24h = f"{float(rate_24h * 100):.4f}%"

        dual = deps.algorithm_confluence
        context.update(
            {
                "order_flow_compact": format_order_flow_compact(deps.order_flow),
                "algorithm_confluence_long": dual.long.model_dump(),
                "algorithm_confluence_short": dual.short.model_dump(),
                "detected_side": dual.detected_side,
                "account_state": deps.account_state.model_dump(),
                "analyst_result": analyst_result,
                "futures_leverage": deps.leverage,
                "liquidation_distance_percent": round(100 / deps.leverage, 1),
                "open_positions_json": positions_text,
                "funding_rate_24h_percent": funding_24h,
            }
        )
        logger.debug(
            "Built trader context for %s: %d keys",
            deps.symbol,
            len(context),
        )
        return context
