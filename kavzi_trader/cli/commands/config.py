"""
Configuration commands for the KavziTrader CLI.
"""

import logging

import click
from pydantic import SecretStr

from kavzi_trader.config import AppConfig

logger = logging.getLogger(__name__)


def _secret_state(secret: SecretStr) -> str:
    return "set" if secret.get_secret_value() else "missing"


@click.command("config")
@click.option(
    "--validate",
    is_flag=True,
    help="Validate the configuration without running any command",
)
@click.option(
    "--paper",
    is_flag=True,
    help="Validate for paper trading instead of live trading",
)
@click.pass_context
def config_command(ctx: click.Context, validate: bool, paper: bool) -> None:
    """Validate the current configuration."""
    if not validate:
        click.echo("Use --validate to validate the configuration")
        return

    app_config: AppConfig = ctx.obj["app_config"]
    mode = "paper" if paper else "live"
    try:
        if paper:
            app_config.validate_for_paper_trading()
        else:
            app_config.validate_for_trading()
    except ValueError as exc:
        logger.warning("Configuration invalid for %s mode", mode)
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Configuration is valid for {mode} trading")
    click.echo(f"Symbols: {', '.join(app_config.trading.symbols)}")
    click.echo(f"Interval: {app_config.trading.interval}")
    click.echo(f"Binance API key: {_secret_state(app_config.api.binance.api_key)}")
    click.echo(
        f"Binance API secret: {_secret_state(app_config.api.binance.api_secret)}",
    )
    click.echo(
        f"OpenRouter API key: {_secret_state(app_config.brain.openrouter_api_key)}",
    )
    click.echo(
        f"Anthropic API key: {_secret_state(app_config.brain.anthropic_api_key)}",
    )
