"""
Data management commands for the KavziTrader CLI.
"""

import click


@click.group()
def data() -> None:
    """Data management commands."""
