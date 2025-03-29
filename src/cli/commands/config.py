"""
Configuration commands for the KavziTrader CLI.
"""

import click

from src.commons.logging import get_logger
from src.config.hydra_util import print_config

# Initialize logger
logger = get_logger(name="kavzitrader.cli.config")


@click.command("config")
@click.option("--show", is_flag=True, help="Show the current configuration")
@click.option(
    "--validate",
    is_flag=True,
    help="Validate the configuration without running any command",
)
@click.pass_context
def config_command(ctx: click.Context, show: bool, validate: bool) -> None:
    """
    Show or validate the current configuration.

    Args:
        show: Whether to show the configuration
        validate: Whether to validate the configuration
    """
    # Access the configuration from the context
    config = ctx.obj.get("config")
    app_config = ctx.obj.get("app_config")

    if show and config:
        print_config(config)
        return

    if validate:
        click.echo("Configuration is valid")
        click.echo(f"App Config: {app_config}")
        return

    click.echo("Use --show to display the current configuration")
    click.echo("Use --validate to validate the configuration")
