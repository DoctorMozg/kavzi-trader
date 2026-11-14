import logging
import time

from pydantic_ai import Agent

from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.prompts.loader import PromptLoader

logger = logging.getLogger(__name__)


class PromptedAgent[TDeps, TOutput]:
    """Shared plumbing for the Analyst and Trader LLM wrappers."""

    _label: str

    def __init__(
        self,
        agent: Agent[TDeps, TOutput],
        prompt_loader: PromptLoader,
        context_builder: ContextBuilder,
    ) -> None:
        self._agent = agent
        self._prompt_loader = prompt_loader
        self._context_builder = context_builder

    async def _run_llm(
        self,
        symbol: str,
        user_prompt: str,
        deps: TDeps,
    ) -> tuple[TOutput, float]:
        """Run the agent, log token usage and return (output, elapsed_ms)."""
        t0 = time.monotonic()
        result = await self._agent.run(user_prompt, deps=deps)
        elapsed_ms = (time.monotonic() - t0) * 1000
        usage = result.usage
        logger.info(
            "%s usage for %s: input_tokens=%d output_tokens=%d "
            "total_tokens=%d elapsed_ms=%.1f",
            self._label,
            symbol,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
            elapsed_ms,
            extra={
                "symbol": symbol,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )
        return result.output, elapsed_ms
