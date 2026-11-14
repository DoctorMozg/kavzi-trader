import logging
from decimal import Decimal

from kavzi_trader.brain.agent.router_config import RouterConfigSchema
from kavzi_trader.brain.geometry.calculator import TradeGeometryCalculator
from kavzi_trader.brain.geometry.schemas import GeometryInputsSchema
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema

logger = logging.getLogger(__name__)


def wait_decision(reasoning: str, confidence: float = 0.0) -> TradeDecisionSchema:
    """Build a structure-less WAIT decision for deterministic reject paths."""
    return TradeDecisionSchema(
        action="WAIT",
        confidence=confidence,
        reasoning=reasoning,
        entry_tactic=None,
        entry_level_index=None,
        stop_level_index=None,
        stop_atr_multiplier=None,
        target_style=None,
    )


def geometry_inputs(
    analyst_result: AnalystDecisionSchema,
    deps: TradingDependenciesSchema,
) -> GeometryInputsSchema:
    """Assemble geometry-calculator inputs from the pipeline context."""
    return GeometryInputsSchema(
        symbol=deps.symbol,
        current_price=deps.current_price,
        atr_14=deps.indicators.atr_14,
        key_levels=analyst_result.key_levels.levels,
        leverage=deps.leverage,
    )


class PreTraderGates:
    """Deterministic checks that skip the Trader LLM on hopeless setups."""

    def __init__(
        self,
        router_config: RouterConfigSchema,
        geometry: TradeGeometryCalculator,
    ) -> None:
        self._router_config = router_config
        self._geometry = geometry

    def check(
        self,
        symbol: str,
        scout_pattern: str | None,
        analyst_result: AnalystDecisionSchema,
        deps: TradingDependenciesSchema,
    ) -> TradeDecisionSchema | None:
        """Run deterministic pre-Trader gates. Returns a WAIT decision if
        any gate rejects, else None to proceed to the LLM call.
        """
        breakout_reject = self.pre_trader_breakout_check(
            symbol,
            scout_pattern,
            deps,
            analyst_direction=analyst_result.direction,
        )
        if breakout_reject is not None:
            return breakout_reject
        return self.pre_trader_viability_check(symbol, analyst_result, deps)

    def pre_trader_breakout_check(
        self,
        symbol: str,
        scout_pattern: str | None,
        deps: TradingDependenciesSchema,
        *,
        analyst_direction: str,
    ) -> TradeDecisionSchema | None:
        """Reject BREAKOUT entries when %B indicates overextension."""
        if scout_pattern != "BREAKOUT":
            return None
        bb = deps.indicators.bollinger
        if bb is None:
            return None
        percent_b = bb.percent_b

        overextended_long = self._router_config.breakout_overextended_b_long
        overextended_short = self._router_config.breakout_overextended_b_short

        is_short = analyst_direction == "SHORT"
        if is_short:
            overextended = percent_b < overextended_short
        else:
            overextended = percent_b > overextended_long

        if overextended:
            if is_short:
                threshold = overextended_short
                band_desc = "below the lower band"
            else:
                threshold = overextended_long
                band_desc = "beyond the upper band"
            logger.info(
                "Pre-Trader BREAKOUT reject for %s: %%B=%.2f,"
                " direction=%s — price overextended %s",
                symbol,
                float(percent_b),
                analyst_direction,
                band_desc,
            )
            return wait_decision(
                f"Deterministic pre-Trader reject: BREAKOUT pattern with"
                f" Bollinger %B={float(percent_b):.2f} exceeds"
                f" {float(threshold):.2f} overextension"
                f" threshold. Price is too far {band_desc} for"
                f" a sustainable breakout entry."
            )

        if is_short:
            in_caution = (
                percent_b < Decimal("-0.10") and percent_b >= overextended_short
            )
        else:
            in_caution = percent_b > Decimal("1.10") and percent_b <= overextended_long
        if in_caution:
            logger.warning(
                "BREAKOUT caution for %s: %%B=%.2f, direction=%s"
                " — approaching overextension zone",
                symbol,
                float(percent_b),
                analyst_direction,
            )
        return None

    def pre_trader_viability_check(
        self,
        symbol: str,
        analyst_result: AnalystDecisionSchema,
        deps: TradingDependenciesSchema,
    ) -> TradeDecisionSchema | None:
        """Skip the Trader LLM when no legal geometry can reach min R:R.

        Uses the geometry calculator's estimate mode (tightest legal stop
        against the best available target), so a block here means even the
        most favourable structural choice cannot produce a viable trade.
        NEUTRAL fails open — there is no direction to size against.
        """
        if analyst_result.direction == "NEUTRAL":
            return None
        viability = self._geometry.estimate(
            analyst_result.direction,
            geometry_inputs(analyst_result, deps),
        )
        if viability.viable:
            return None
        logger.warning(
            "Pre-Trader viability block for %s: %s",
            symbol,
            viability.reason,
            extra={"symbol": symbol, "agent": "trader"},
        )
        return wait_decision(
            f"Pre-trader viability block: {viability.reason}"
            f" Skipping Trader call — no structural choice can produce"
            f" a valid trade here."
        )
