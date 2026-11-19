"""
Trading commands for the KavziTrader CLI.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import click

from kavzi_trader.cli.composition import (
    OrchestratorComposer,
    build_exchange,
    build_state_manager,
)
from kavzi_trader.config import AppConfig
from kavzi_trader.events.aggregate_type import AggregateType
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.infra.redis_client import RedisStateClient
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


@click.group()
def trade() -> None:
    """Trading commands."""


async def _start_orchestrator(
    app_config: AppConfig,
    paper: bool = False,
    paper_balance: float | None = None,
) -> None:
    composer = OrchestratorComposer(app_config, paper, paper_balance)
    orchestrator = await composer.compose()
    await orchestrator.start()


@trade.command()
@click.option("--dry-run", is_flag=True)
@click.option(
    "--paper",
    is_flag=True,
    help="Paper trading mode with simulated orders and live market data.",
)
@click.option(
    "--paper-balance",
    type=float,
    default=None,
    help="Initial paper balance in USDT (default: from config or 10000).",
)
@click.pass_context
def start(
    ctx: click.Context,
    dry_run: bool,
    paper: bool,
    paper_balance: float | None,
) -> None:
    """Start the trading orchestrator."""
    app_config = ctx.obj["app_config"]
    if dry_run:
        click.echo("Dry run: orchestrator not started")
        return
    if paper:
        balance_display = (
            paper_balance
            if paper_balance is not None
            else app_config.paper.initial_balance_usdt
        )
        click.echo("=" * 60)
        click.echo("  PAPER FUTURES TRADING MODE")
        click.echo(f"  Initial balance: {balance_display} USDT")
        click.echo(f"  Default leverage: {app_config.futures.default_leverage}x")
        click.echo(f"  Margin type: {app_config.futures.margin_type}")
        click.echo(f"  Commission rate: {app_config.paper.commission_rate}")
        click.echo(
            "  Orders are simulated. Market data is LIVE.",
        )
        click.echo("=" * 60)
    asyncio.run(
        _start_orchestrator(
            app_config,
            paper=paper,
            paper_balance=paper_balance,
        ),
    )


@asynccontextmanager
async def _connected_state(app_config: AppConfig) -> AsyncIterator[StateManager]:
    exchange = build_exchange(app_config)
    try:
        state_manager = build_state_manager(app_config, exchange)
        await state_manager.connect()
        try:
            yield state_manager
        finally:
            await state_manager.close()
    finally:
        await exchange.close()


async def _show_status(app_config: AppConfig) -> None:
    async with _connected_state(app_config) as state_manager:
        positions = await state_manager.get_all_positions()
        orders = await state_manager.get_open_orders()
    click.echo(f"Positions: {len(positions)}")
    click.echo(f"Open orders: {len(orders)}")


@trade.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current trading system status."""
    asyncio.run(_show_status(ctx.obj["app_config"]))


async def _list_positions(app_config: AppConfig) -> None:
    async with _connected_state(app_config) as state_manager:
        positions = await state_manager.get_all_positions()
    if not positions:
        click.echo("No open positions")
        return
    for position in positions:
        click.echo(
            f"{position.symbol} {position.side} qty={position.quantity} "
            f"entry={position.entry_price} sl={position.stop_loss} "
            f"tp={position.take_profit}",
        )


@trade.command()
@click.pass_context
def positions(ctx: click.Context) -> None:
    """List open positions."""
    asyncio.run(_list_positions(ctx.obj["app_config"]))


async def _show_history(app_config: AppConfig) -> None:
    redis_client = RedisStateClient(app_config.redis)
    await redis_client.connect()
    try:
        store = RedisEventStore(redis_client, app_config.events)
        events = await store.read(
            app_config.events.streams[AggregateType.POSITIONS],
            count=10,
        )
    finally:
        await redis_client.close()
    if not events:
        click.echo("No recent events")
        return
    for event in events:
        click.echo(f"{event.timestamp.isoformat()} {event.event_type}")


@trade.command()
@click.pass_context
def history(ctx: click.Context) -> None:
    """Show recent execution history from event store."""
    asyncio.run(_show_history(ctx.obj["app_config"]))
