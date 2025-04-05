"""
Configuration commands for the KavziTrader CLI.
"""

import logging

import click

# Initialize logger
logger = logging.getLogger(__name__)


@click.command("config")
@click.option(
    "--validate",
    is_flag=True,
    help="Validate the configuration without running any command",
)
@click.pass_context
def config_command(ctx: click.Context, validate: bool) -> None:
    """
    Show or validate the current configuration.

    Args:
        show: Whether to show the configuration
        validate: Whether to validate the configuration
    """
    # Access the configuration from the context
    app_config = ctx.obj.get("app_config")

    if validate:
        click.echo("Configuration is valid")
        click.echo(f"App Config: {app_config}")
        return

    click.echo("Use --show to display the current configuration")
    click.echo("Use --validate to validate the configuration")
