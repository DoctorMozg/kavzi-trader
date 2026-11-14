"""
Model management commands for the KavziTrader CLI.
"""

import asyncio
import logging

import click
from openai import AsyncOpenAI

from kavzi_trader.brain.config import ANTHROPIC_AGENT_DEFAULTS, AgentModelConfigSchema
from kavzi_trader.config import AppConfig

logger = logging.getLogger(__name__)


def _describe(tier: AgentModelConfigSchema, role: str) -> str:
    model_id = tier.model_id or ANTHROPIC_AGENT_DEFAULTS[role].model_id
    return f"{model_id} ({tier.provider})"


@click.group()
def model() -> None:
    """Model management commands."""


@model.command("status")
@click.pass_context
def model_status(ctx: click.Context) -> None:
    """Show status of active LLM connections."""
    app_config: AppConfig = ctx.obj["app_config"]
    brain = app_config.brain

    if not brain.openrouter_api_key.get_secret_value():
        click.echo("OpenRouter: NOT CONFIGURED (set KT_OPENROUTER_API_KEY)")
        return

    click.echo(f"OpenRouter base URL: {brain.openrouter_base_url}")
    click.echo("Scout:         algorithmic (no LLM)")
    click.echo(f"Analyst model: {_describe(brain.analyst, 'analyst')}")
    click.echo(f"Trader model:  {_describe(brain.trader, 'trader')}")

    async def _check() -> bool:
        client = AsyncOpenAI(
            base_url=brain.openrouter_base_url,
            api_key=brain.openrouter_api_key.get_secret_value(),
        )
        try:
            await client.models.list()
        except Exception:
            logger.exception("OpenRouter connectivity check failed")
            return False
        else:
            return True

    connected = asyncio.run(_check())
    click.echo(f"Connection: {'OK' if connected else 'FAILED'}")
