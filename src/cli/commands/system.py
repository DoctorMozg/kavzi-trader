"""
System management commands for the KavziTrader CLI.
"""

import click

from src.commons.logging import get_logger

# Initialize logger
logger = get_logger(name="kavzitrader.cli.system")


@click.group()
def system() -> None:
    """System management commands."""


@system.command("setup")
@click.option("--database", is_flag=True, help="Initialize database")
@click.option("--force", is_flag=True, help="Force setup (overwrite)")
@click.pass_context
def setup_system(database: bool, force: bool) -> None:
    """
    Set up the system with the specified components.

    Args:
        database: Whether to initialize the database
        force: Whether to force setup (overwrite)
    """
    click.echo("Setting up system")
    click.echo(f"Initialize database: {database}")
    click.echo(f"Force: {force}")
