import hashlib
import logging

from kavzi_trader.brain.agent.prompted_agent import PromptedAgent
from kavzi_trader.brain.schemas.dependencies import AnalystDependenciesSchema
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema

logger = logging.getLogger(__name__)


class AnalystAgent(PromptedAgent[AnalystDependenciesSchema, AnalystDecisionSchema]):
    """
    Performs detailed setup validation after the scout flags interest.
    """

    _label = "Analyst"

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        logger.debug("Analyst building context for %s", deps.symbol)
        context = self._context_builder.build_analyst_context(deps)
        user_prompt = self._prompt_loader.render_user_prompt("analyze_setup", context)
        prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:12]
        output, _ = await self._run_llm(deps.symbol, user_prompt, deps)
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
