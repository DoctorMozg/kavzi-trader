from typing import cast

from pydantic_ai import Agent

from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.dependencies import AnalystDependenciesSchema


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
        context = self._context_builder.build_analyst_context(deps)
        user_prompt = self._prompt_loader.render_user_prompt("analyze_setup", context)
        result = await self._agent.run(user_prompt, deps=deps)
        return cast(AnalystDecisionSchema, result.output)
