import logging
import time
from typing import cast

from pydantic_ai import Agent

from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.dependencies import ScoutDependenciesSchema
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema

logger = logging.getLogger(__name__)


class ScoutAgent:
    """
    Runs fast triage to decide if a candle is worth deeper analysis.
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

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        logger.debug("Scout building context for %s", deps.symbol)
        context = self._context_builder.build_scout_context(deps)
        user_prompt = self._prompt_loader.render_user_prompt("scout_scan", context)
        t0 = time.monotonic()
        result = await self._agent.run(user_prompt, deps=deps)
        elapsed_ms = (time.monotonic() - t0) * 1000
        output = cast(ScoutDecisionSchema, result.output)
        logger.info(
            "Scout result for %s: verdict=%s reason=%s pattern=%s elapsed_ms=%.1f",
            deps.symbol,
            output.verdict,
            output.reason,
            output.pattern_detected,
            elapsed_ms,
            extra={"symbol": deps.symbol, "elapsed_ms": round(elapsed_ms, 1)},
        )
        return output
