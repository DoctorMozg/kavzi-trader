import logging

from kavzi_trader.brain.agent.prompted_agent import PromptedAgent
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema

logger = logging.getLogger(__name__)


class TraderAgent(PromptedAgent[TradingDependenciesSchema, TradeDecisionSchema]):
    """
    Produces the final trade decision and management parameters.
    """

    _label = "Trader"

    async def run(
        self,
        deps: TradingDependenciesSchema,
        analyst_result: AnalystDecisionSchema | None = None,
        scout_pattern: str | None = None,
    ) -> TradeDecisionSchema:
        logger.debug("Trader building context for %s", deps.symbol)
        context = self._context_builder.build_trader_context(
            deps,
            analyst_result=analyst_result,
            scout_pattern=scout_pattern,
        )
        user_prompt = self._prompt_loader.render_user_prompt("make_decision", context)
        output, elapsed_ms = await self._run_llm(deps.symbol, user_prompt, deps)
        logger.info(
            "Trader result for %s: action=%s confidence=%.2f "
            "entry_tactic=%s entry_idx=%s stop_idx=%s stop_atr=%s "
            "target=%s elapsed_ms=%.1f",
            deps.symbol,
            output.action,
            output.confidence,
            output.entry_tactic,
            output.entry_level_index,
            output.stop_level_index,
            output.stop_atr_multiplier,
            output.target_style,
            elapsed_ms,
            extra={"symbol": deps.symbol, "elapsed_ms": round(elapsed_ms, 1)},
        )
        logger.debug(
            "Trader reasoning for %s: %s",
            deps.symbol,
            output.reasoning,
        )
        return output
