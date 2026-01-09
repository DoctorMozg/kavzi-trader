"""
Trading commands for the KavziTrader CLI.
"""

import click


@click.group()
def trade() -> None:
    """Trading commands."""
