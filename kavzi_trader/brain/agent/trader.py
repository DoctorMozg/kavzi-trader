import logging
import time
from typing import cast

from pydantic_ai import Agent

from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.dependencies import TradingDependenciesSchema

logger = logging.getLogger(__name__)


class TraderAgent:
    """
    Produces the final trade decision and management parameters.
    """

    def __init__(
        self,
        agent: Agent,
        prompt_loader: PromptLoader,
        context_builder: ContextBuilder,
    ) -> None:
        self._agent = agent
        self._prompt_loader = prompt_loader
        self._context_builder = context_builder

    async def run(self, deps: TradingDependenciesSchema) -> TradeDecisionSchema:
        logger.debug("Trader building context for %s", deps.symbol)
        context = self._context_builder.build_trader_context(deps)
        user_prompt = self._prompt_loader.render_user_prompt("make_decision", context)
        t0 = time.monotonic()
        result = await self._agent.run(user_prompt, deps=deps)
        elapsed_ms = (time.monotonic() - t0) * 1000
        output = cast(TradeDecisionSchema, result.output)
        logger.info(
            "Trader result for %s: action=%s confidence=%.2f "
            "entry=%s SL=%s TP=%s elapsed_ms=%.1f",
            deps.symbol,
            output.action,
            output.confidence,
            output.suggested_entry,
            output.suggested_stop_loss,
            output.suggested_take_profit,
            elapsed_ms,
            extra={"symbol": deps.symbol, "elapsed_ms": round(elapsed_ms, 1)},
        )
        logger.debug(
            "Trader reasoning for %s: %s",
            deps.symbol,
            output.reasoning,
        )
        return output
