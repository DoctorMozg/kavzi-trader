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

# Import our historical data commands
from src.data.collection.cli.commands import historical_command

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


# Register the historical data commands as a subgroup of data
data.add_command(historical_command)


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

    # Note: Consider redirecting users to the more full-featured historical fetch command
    click.echo(
        "\nTip: For more options, try 'kavzitrader data historical fetch' instead."
    )


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

    click.echo(f"Training model with config: {config_name}")
    click.echo(f"Symbol: {symbol}")
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
        plan: Trading plan file path
        start_date: Backtest start date (YYYY-MM-DD)
        end_date: Backtest end date (YYYY-MM-DD)
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo(f"Running backtest with plan: {plan}")
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
        plan: Trading plan file path
        capital: Initial capital
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo(f"Starting paper trading with plan: {plan}")
    click.echo(f"Initial capital: ${capital}")
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
        plan: Trading plan file path
        check_balance: Whether to verify account balance
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo(f"Starting LIVE TRADING with plan: {plan}")
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
    Set up the system with the specified components.

    Args:
        database: Whether to initialize the database
        force: Whether to force setup (overwrite)
    """
    # Access the configuration from the context
    config = ctx.obj["app_config"]

    click.echo("Setting up system")
    click.echo(f"Initialize database: {database}")
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


@cli.command("test-config")
@click.option(
    "--section",
    default="system",
    help="Configuration section to display (system, data, api, etc.)",
)
@click.argument("hydra_overrides", nargs=-1)
@click.pass_context
def test_config(ctx: click.Context, section: str, hydra_overrides: tuple[str]) -> None:
    """
    Test configuration with the specified hydra overrides.

    Args:
        section: Configuration section to display
        hydra_overrides: Hydra configuration overrides
    """
    from omegaconf import OmegaConf

    # Add any overrides from the argument to the ones from ctx
    ctx_overrides = ctx.obj.get("hydra_overrides", []) if ctx.obj else []
    all_overrides = list(ctx_overrides) + list(hydra_overrides)

    click.echo(f"Testing configuration with section: {section}")
    click.echo(f"Overrides: {all_overrides}")

    # Get Hydra configuration
    config = get_config(overrides=all_overrides)
    # Extract the requested section
    if section in config:
        section_config = config[section]
        click.echo(f"Configuration section '{section}':")
        click.echo(OmegaConf.to_yaml(section_config))
    else:
        click.echo(f"Section '{section}' not found in configuration")
        click.echo("Available sections:")
        for key in config.keys():
            click.echo(f"  - {key}")


if __name__ == "__main__":
    cli(obj={})  # pylint: disable=no-value-for-parameter
