"""
KavziTrader - Neural Network-Based Crypto Trading Platform.

This module serves as the main entry point for the KavziTrader CLI.
"""

import sys
from pathlib import Path

import click

# Add src to path to allow imports from src package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Setup logging
from src.commons.logging import setup_logging
from src.config.hydra_util import (
    config_to_app_config,
    get_config,
    init_hydra,
    print_config,
    resolve_relative_paths,
)

# Initialize logger
logger = setup_logging(name="kavzitrader")

# Initialize Hydra
init_hydra()


class HydraOptionsGroup(click.Group):
    """Custom Group class that captures all unparsed options as Hydra overrides."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Parse arguments and capture unparsed ones for Hydra."""
        # First, let the base class parse the standard options
        parsed_args: list[str] = super().parse_args(ctx, args)

        # Extract any remaining arguments which will be passed to Hydra
        # Format of code: key=value
        hydra_overrides: list[str] = [
            arg for arg in args if "=" in arg and not arg.startswith(("-", "--"))
        ]

        # Store the overrides in the context
        ctx.obj = ctx.obj or {}
        ctx.obj["hydra_overrides"] = hydra_overrides

        return parsed_args


@click.group(cls=HydraOptionsGroup)
@click.version_option()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to configuration directory",
)
@click.option(
    "--config-name",
    help="Name of the configuration to use (without extension)",
)
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
    config: str | None,
    config_dir: str | None,
    config_name: str | None,
) -> None:
    """
    KavziTrader - Neural Network-Based Crypto Trading Platform.

    You can pass hydra configuration overrides as key=value pairs after the command.
    Example:
    kavzitrader
    --verbose model train
    --config-name=transformer model.learning_rate=0.001
    """
    if verbose:
        # Update the log level if verbose mode is enabled
        logger.setLevel("DEBUG")
        logger.debug("Verbose mode enabled")

    # Load environment variables
    from dotenv import load_dotenv

    load_dotenv()  # take environment variables

    # Get Hydra overrides from context
    hydra_overrides = ctx.obj.get("hydra_overrides", []) if ctx.obj else []

    if hydra_overrides:
        logger.debug(f"Hydra overrides from command line: {hydra_overrides}")

    # Prepare Hydra config overrides from config file if specified
    if config:
        logger.info(f"Using configuration file: {config}")
        # We'll handle this custom config file differently
        # by loading it directly instead of through Hydra

    # Load the configuration
    try:
        # Get Hydra configuration
        hydra_config = get_config(
            config_path=config_dir,
            config_name=config_name,
            overrides=hydra_overrides,
        )

        # Resolve relative paths
        hydra_config = resolve_relative_paths(hydra_config)
        # Convert to AppConfig for type safety
        app_config = config_to_app_config(hydra_config)

        # Store in context for child commands
        ctx.obj = ctx.obj or {}
        ctx.obj.update(
            {
                "config": hydra_config,  # Original Hydra config
                "app_config": app_config,  # Pydantic validated config
            },
        )

        logger.info("Configuration loaded successfully")

    except Exception:
        logger.exception("Error loading configuration")
        ctx.fail("Failed to load configuration")


@cli.group()
def data() -> None:
    """Data management commands."""


@data.command("fetch")
@click.option("--symbol", required=True, help="Trading pair symbol")
@click.option("--interval", default="1h", help="Timeframe (1m, 5m, 1h, etc.)")
@click.option("--start-date", help="Start date for historical data (YYYY-MM-DD)")
@click.option("--end-date", help="End date for historical data (YYYY-MM-DD)")
@click.option("--limit", type=int, help="Maximum number of candles")
@click.pass_context
def fetch_data(
    ctx: click.Context,
    symbol: str,
    interval: str,
    start_date: str | None,
    end_date: str | None,
    limit: int | None,
) -> None:
    """
    Fetch historical market data from Binance.

    Args:
        symbol: Trading pair symbol
        interval: Timeframe (1m, 5m, 1h, etc.)
        start_date: Start date for historical data (YYYY-MM-DD)
        end_date: End date for historical data (YYYY-MM-DD)
        limit: Maximum number of candles
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo(f"Fetching {symbol} data with {interval} interval")
    click.echo(f"Start date: {start_date}")
    click.echo(f"End date: {end_date}")
    click.echo(f"Limit: {limit}")
    click.echo(f"Config: {config}")
    # Implementation will be added later


@cli.group()
def model() -> None:
    """Model management commands."""


@model.command("train")
@click.option("--config-name", required=True, help="Model configuration name")
@click.option("--symbol", required=True, help="Trading pair to train on")
@click.pass_context
def train_model(ctx: click.Context, config_name: str, symbol: str) -> None:
    """
    Train a model with the specified configuration.

    Args:
        config_name: Model configuration name
        symbol: Trading pair to train on
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo(f"Training model {config_name} for {symbol}")
    click.echo(f"Config: {config}")
    # Implementation will be added later


@cli.group()
def backtest() -> None:
    """Backtesting commands."""


@backtest.command("run")
@click.option(
    "--plan",
    required=True,
    type=click.Path(exists=True),
    help="Trading plan file",
)
@click.option("--start-date", help="Backtest start date (YYYY-MM-DD)")
@click.option("--end-date", help="Backtest end date (YYYY-MM-DD)")
@click.pass_context
def run_backtest(
    ctx: click.Context,
    plan: str,
    start_date: str | None,
    end_date: str | None,
) -> None:
    """
    Run a backtest with the specified trading plan.

    Args:
        plan: Trading plan file
        start_date: Backtest start date (YYYY-MM-DD)
        end_date: Backtest end date (YYYY-MM-DD)
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo(f"Running backtest with plan {plan}")
    click.echo(f"Start date: {start_date}")
    click.echo(f"End date: {end_date}")
    click.echo(f"Config: {config}")
    # Implementation will be added later


@cli.group()
def trade() -> None:
    """Trading commands."""


@trade.command("paper")
@click.option(
    "--plan",
    required=True,
    type=click.Path(exists=True),
    help="Trading plan file",
)
@click.option("--capital", type=float, default=10000.0, help="Initial capital")
@click.pass_context
def paper_trade(ctx: click.Context, plan: str, capital: float) -> None:
    """
    Run paper trading with the specified trading plan.

    Args:
        plan: Trading plan file
        capital: Initial capital
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo(f"Starting paper trading with plan {plan} and capital {capital}")
    click.echo(f"Config: {config}")
    # Implementation will be added later


@trade.command("live")
@click.option(
    "--plan",
    required=True,
    type=click.Path(exists=True),
    help="Trading plan file",
)
@click.option(
    "--check-balance",
    is_flag=True,
    help="Verify account balance before trading",
)
@click.pass_context
def live_trade(ctx: click.Context, plan: str, check_balance: bool) -> None:
    """
    Run live trading with the specified trading plan.

    Args:
        plan: Trading plan file
        check_balance: Verify account balance before trading
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo(f"Starting live trading with plan {plan}")
    click.echo(f"Check balance: {check_balance}")
    click.echo(f"Config: {config}")
    # Implementation will be added later


@cli.group()
def system() -> None:
    """System management commands."""


@system.command("setup")
@click.option("--database", is_flag=True, help="Initialize database")
@click.option("--force", is_flag=True, help="Force setup (overwrite)")
@click.pass_context
def setup_system(ctx: click.Context, database: bool, force: bool) -> None:
    """
    Set up system components.

    Args:
        database: Initialize database
        force: Force setup (overwrite)
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    if database:
        click.echo("Initializing database")
        click.echo(f"Force: {force}")
        click.echo(f"Config: {config}")
        # Implementation will be added later


@cli.command("config")
@click.option("--show", is_flag=True, help="Show the current configuration")
@click.option(
    "--validate",
    is_flag=True,
    help="Validate the configuration without running any command",
)
@click.pass_context
def config_command(ctx: click.Context, show: bool, validate: bool) -> None:
    """
    Manage configuration settings.

    Args:
        show: Show the current configuration
        validate: Validate the configuration without running any command
    """
    if show:
        # Access the configuration from the context
        hydra_config = ctx.obj["config"]
        print_config(hydra_config)

    if validate:
        # We've already validated the config when loading it, so just report success
        click.echo("Configuration validation successful")


@cli.command("test-config")
@click.option(
    "--section",
    default="system",
    help="Configuration section to display (system, data, api, etc.)",
)
@click.argument("hydra_overrides", nargs=-1)
@click.pass_context
def test_config(ctx: click.Context, section: str, hydra_overrides: tuple[str]) -> None:  # noqa: ARG001
    """
    Test command to demonstrate Hydra configuration integration.

    This command displays values from the specified section of the configuration.
    You can override these values using Hydra syntax, for example:

    kavzitrader test-config --section=system system.log_level=DEBUG

    Args:
        section: Configuration section to display
    """
    # Access the Hydra configuration from the context
    hydra_config = ctx.obj["config"]

    click.echo(f"\nTesting configuration - Section: {section}")
    click.echo("=" * 50)

    # Display the requested section
    if section in hydra_config:
        section_config = hydra_config[section]
        for key, value in section_config.items():
            click.echo(f"{section}.{key}: {value}")
    else:
        available_sections = ", ".join(hydra_config.keys())
        click.echo(
            f"Section '{section}' not found. Available sections: {available_sections}",
        )

    click.echo("\nFull configuration can be displayed with 'kavzitrader config --show'")


if __name__ == "__main__":
    cli(obj={})
