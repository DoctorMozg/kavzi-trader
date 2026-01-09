"""
Model management commands for the KavziTrader CLI.
"""

import logging

import click

logger = logging.getLogger(__name__)


@click.group()
def model() -> None:
    """Model management commands."""


@model.command("status")
def model_status() -> None:
    """Show status of active LLM connections."""
    click.echo("LLM integration is not configured yet.")
