import logging
from decimal import Decimal
from typing import cast

from pydantic import BaseModel, ConfigDict

from kavzi_trader.brain.context.context_dicts import (
    AccountStateDict,
    AnalystContextDict,
    ATRFallbackTargetDict,
    ConfluenceBlockDict,
    MarketContextDict,
    TraderContextDict,
)
from kavzi_trader.brain.context.formatters import (
    format_candles_table,
    format_indicators_compact,
    format_order_flow_compact,
)
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.orchestrator.loops.confluence_thresholds import (
    confluence_enter_min_for_regime,
)
from kavzi_trader.spine.confluence import side_trim_confluence

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
    ) -> MarketContextDict:
        """Build the shared market context dict for Analyst/Trader prompts.

        We used to also serialize a full ``MarketSnapshotSchema.model_dump()``
        here. Its fields overlapped completely with ``candles_table`` +
        ``indicators_compact`` and alone added ~5k tokens per prompt. Templates
        read the flat scalars below instead.
        """
        atr_14 = deps.indicators.atr_14
        return MarketContextDict(
            candles_table=format_candles_table(deps.recent_candles),
            indicators_compact=format_indicators_compact(
                deps.indicators, reference_price=deps.current_price
            ),
            symbol=deps.symbol,
            timeframe=deps.timeframe,
            current_price=str(deps.current_price),
            volatility_regime=deps.volatility_regime.value,
            atr_14=str(atr_14) if atr_14 is not None else None,
        )

    def build_analyst_context(
        self,
        deps: AnalystDependenciesSchema,
    ) -> AnalystContextDict:
        self._warn_if_broken_data(deps.symbol, deps)
        market = self._build_market_context(deps)
        dual = deps.algorithm_confluence
        sentiment = deps.sentiment_summary
        long_block, short_block = side_trim_confluence(
            cast("ConfluenceBlockDict", dual.long.model_dump()),
            cast("ConfluenceBlockDict", dual.short.model_dump()),
            dual.detected_side,
        )
        context = AnalystContextDict(
            candles_table=market["candles_table"],
            indicators_compact=market["indicators_compact"],
            symbol=market["symbol"],
            timeframe=market["timeframe"],
            current_price=market["current_price"],
            volatility_regime=market["volatility_regime"],
            atr_14=market["atr_14"],
            order_flow_compact=format_order_flow_compact(deps.order_flow),
            algorithm_confluence_long=long_block,
            algorithm_confluence_short=short_block,
            detected_side=dual.detected_side,
            futures_leverage=deps.leverage,
            symbol_tier=deps.symbol_tier,
            tier_min_confidence=str(deps.tier_min_confidence),
            confluence_enter_min=confluence_enter_min_for_regime(
                deps.volatility_regime,
            ),
            sentiment_summary=sentiment.summary if sentiment else None,
            sentiment_bias=(sentiment.sentiment_bias if sentiment else None),
            sentiment_confidence_adjustment=(
                str(sentiment.confidence_adjustment) if sentiment else None
            ),
        )
        logger.debug(
            "Built analyst context for %s: %d keys",
            deps.symbol,
            len(context),
        )
        return context

    @staticmethod
    def _compute_atr_fallback_targets(
        analyst_result: AnalystDecisionSchema | None,
        current_price: Decimal,
        atr: Decimal | None,
    ) -> list[ATRFallbackTargetDict]:
        """Inject ATR-projected TP targets alongside analyst key_levels."""
        if analyst_result is None or atr is None or atr == Decimal(0):
            return []

        direction = analyst_result.direction
        if direction == "NEUTRAL":
            return []

        multipliers = [Decimal("2.0"), Decimal("3.0")]
        targets: list[ATRFallbackTargetDict] = []
        for mult in multipliers:
            if direction == "LONG":
                price = current_price + mult * atr
            else:
                price = current_price - mult * atr
            targets.append(
                ATRFallbackTargetDict(
                    price=str(price),
                    label=f"ATR projection {mult}x",
                ),
            )

        logger.info(
            "ATR projection targets for %s %s: %s",
            analyst_result.direction,
            current_price,
            [t["price"] for t in targets],
        )
        return targets

    def build_trader_context(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
        scout_pattern: str | None = None,
    ) -> TraderContextDict:
        self._warn_if_broken_data(deps.symbol, deps)
        market = self._build_market_context(deps)
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
            # Funding settles every 8h on Binance perpetuals, so *3 projects
            # the 24h cost. Preserve sign: positive means longs pay shorts,
            # negative means shorts pay longs — dropping the sign loses
            # directional bias that the Trader LLM needs.
            rate_24h = deps.order_flow.funding_rate * 3
            funding_24h = f"{float(rate_24h * 100):+.4f}%"

        dual = deps.algorithm_confluence
        sentiment = deps.sentiment_summary
        atr_fallback = self._compute_atr_fallback_targets(
            analyst_result=analyst_result,
            current_price=deps.current_price,
            atr=deps.indicators.atr_14,
        )
        long_block, short_block = side_trim_confluence(
            cast("ConfluenceBlockDict", dual.long.model_dump()),
            cast("ConfluenceBlockDict", dual.short.model_dump()),
            dual.detected_side,
        )
        context = TraderContextDict(
            candles_table=market["candles_table"],
            indicators_compact=market["indicators_compact"],
            symbol=market["symbol"],
            timeframe=market["timeframe"],
            current_price=market["current_price"],
            volatility_regime=market["volatility_regime"],
            atr_14=market["atr_14"],
            order_flow_compact=format_order_flow_compact(deps.order_flow),
            algorithm_confluence_long=long_block,
            algorithm_confluence_short=short_block,
            detected_side=dual.detected_side,
            account_state=cast("AccountStateDict", deps.account_state.model_dump()),
            analyst_result=analyst_result,
            futures_leverage=deps.leverage,
            liquidation_distance_percent=round(100 / deps.leverage, 1),
            open_positions_json=positions_text,
            funding_rate_24h_percent=funding_24h,
            scout_pattern=scout_pattern,
            symbol_tier=deps.symbol_tier,
            tier_min_confidence=str(deps.tier_min_confidence),
            sentiment_summary=sentiment.summary if sentiment else None,
            sentiment_bias=(sentiment.sentiment_bias if sentiment else None),
            sentiment_confidence_adjustment=(
                str(sentiment.confidence_adjustment) if sentiment else None
            ),
            atr_fallback_targets=atr_fallback,
        )
        logger.debug(
            "Built trader context for %s: %d keys",
            deps.symbol,
            len(context),
        )
        return context
