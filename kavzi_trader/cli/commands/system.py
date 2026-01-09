"""
System management commands for the KavziTrader CLI.
"""

import click


@click.group()
def system() -> None:
    """System management commands."""
