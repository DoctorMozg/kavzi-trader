from pathlib import Path
from typing import Any, Literal, cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, ConfigDict


class PromptPathsSchema(BaseModel):
    system: dict[str, str]
    user: dict[str, str]

    model_config = ConfigDict(frozen=True)


class PromptLoader:
    """
    Renders Jinja2 templates for system and user prompts.
    """

    def __init__(self, templates_path: Path | None = None) -> None:
        base_path = templates_path or Path(__file__).resolve().parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(base_path),
            undefined=StrictUndefined,
            autoescape=select_autoescape(default_for_string=False, default=False),
        )
        self._paths = PromptPathsSchema(
            system={
                "scout": "system/agents/scout.j2",
                "analyst": "system/agents/analyst.j2",
                "trader": "system/agents/trader.j2",
            },
            user={
                "scout_scan": "user/requests/scout_scan.j2",
                "analyze_setup": "user/requests/analyze_setup.j2",
                "make_decision": "user/requests/make_decision.j2",
            },
        )

    def render_system_prompt(self, agent: Literal["scout", "analyst", "trader"]) -> str:
        template_path = self._paths.system[agent]
        return cast("str", self._env.get_template(template_path).render())

    def render_user_prompt(
        self,
        request: Literal["scout_scan", "analyze_setup", "make_decision"],
        context: dict[str, Any],
    ) -> str:
        template_path = self._paths.user[request]
        return cast("str", self._env.get_template(template_path).render(**context))
