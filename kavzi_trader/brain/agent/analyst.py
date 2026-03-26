import logging
import time
from typing import cast

from pydantic_ai import Agent

from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.dependencies import AnalystDependenciesSchema

logger = logging.getLogger(__name__)


class AnalystAgent:
    """
    Performs detailed setup validation after the scout flags interest.
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

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        logger.debug("Analyst building context for %s", deps.symbol)
        context = self._context_builder.build_analyst_context(deps)
        user_prompt = self._prompt_loader.render_user_prompt("analyze_setup", context)
        t0 = time.monotonic()
        result = await self._agent.run(user_prompt, deps=deps)
        elapsed_ms = (time.monotonic() - t0) * 1000
        output = cast("AnalystDecisionSchema", result.output)
        logger.info(
            "Analyst result for %s: setup_valid=%s direction=%s "
            "confluence=%d elapsed_ms=%.1f",
            deps.symbol,
            output.setup_valid,
            output.direction,
            output.confluence_score,
            elapsed_ms,
            extra={"symbol": deps.symbol, "elapsed_ms": round(elapsed_ms, 1)},
        )
        logger.debug(
            "Analyst reasoning for %s: %s",
            deps.symbol,
            output.reasoning,
        )
        return output
