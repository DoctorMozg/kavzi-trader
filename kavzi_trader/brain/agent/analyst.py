import hashlib
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
        prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:12]
        t0 = time.monotonic()
        result = await self._agent.run(user_prompt, deps=deps)
        elapsed_ms = (time.monotonic() - t0) * 1000
        output = cast("AnalystDecisionSchema", result.output)
        usage = result.usage()
        logger.info(
            "Analyst usage for %s: request_tokens=%d response_tokens=%d "
            "total_tokens=%d elapsed_ms=%.1f",
            deps.symbol,
            usage.request_tokens or 0,
            usage.response_tokens or 0,
            usage.total_tokens or 0,
            elapsed_ms,
            extra={
                "symbol": deps.symbol,
                "request_tokens": usage.request_tokens,
                "response_tokens": usage.response_tokens,
                "total_tokens": usage.total_tokens,
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )
        logger.info(
            "Analyst result for %s: setup_valid=%s direction=%s "
            "confluence=%d prompt_hash=%s",
            deps.symbol,
            output.setup_valid,
            output.direction,
            output.confluence_score,
            prompt_hash,
            extra={
                "symbol": deps.symbol,
                "prompt_hash": prompt_hash,
            },
        )
        logger.debug(
            "Analyst reasoning for %s: %s",
            deps.symbol,
            output.reasoning,
        )
        return output
