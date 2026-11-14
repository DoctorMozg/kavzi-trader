"""
Real-time dashboard commands for the KavziTrader CLI.
"""

import asyncio
import logging

import click
import uvicorn
from redis.asyncio import Redis

from kavzi_trader.config import AppConfig
from kavzi_trader.ui.demo_feed import UiDemoFeed
from kavzi_trader.ui.redis_publisher import RedisUiPublisher
from kavzi_trader.ui.schema_export import UI_SCHEMA_PATH, render_ui_schema
from kavzi_trader.ui.server.app import UiWebApp
from kavzi_trader.ui.server.broadcaster import UiBroadcaster
from kavzi_trader.ui.server.projection import UiStateProjection
from kavzi_trader.ui.server.stream_service import UiStreamService

logger = logging.getLogger(__name__)

# redis-py 8 defaults socket_timeout to 5s; XREAD BLOCK needs headroom above it.
_SOCKET_TIMEOUT_MARGIN_S = 8.0


def _redis_client(app_config: AppConfig, socket_timeout_s: float) -> Redis:  # type: ignore[type-arg]
    return Redis(
        host=app_config.redis.host,
        port=app_config.redis.port,
        db=app_config.redis.db,
        password=app_config.redis.password,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=socket_timeout_s,
    )


@click.group()
def ui() -> None:
    """Real-time WebSocket dashboard."""


@ui.command()
@click.option("--host", default=None, help="Bind address (default from config)")
@click.option("--port", type=int, default=None, help="Bind port (default from config)")
@click.pass_context
def serve(ctx: click.Context, host: str | None, port: int | None) -> None:
    """Serve the dashboard and stream trader events to browsers."""
    app_config: AppConfig = ctx.obj["app_config"]
    ui_config = app_config.ui
    redis = _redis_client(
        app_config,
        socket_timeout_s=ui_config.read_block_ms / 1000 + _SOCKET_TIMEOUT_MARGIN_S,
    )
    projection = UiStateProjection(ui_config)
    broadcaster = UiBroadcaster(ui_config.client_queue_size)
    app = UiWebApp(
        projection=projection,
        broadcaster=broadcaster,
        stream_service=UiStreamService(redis, ui_config, projection, broadcaster),
        static_dir=ui_config.static_dir,
    ).build()
    bind_host = host or ui_config.host
    bind_port = port or ui_config.port
    click.echo(f"Dashboard: http://{bind_host}:{bind_port}")
    # log_config=None keeps the project's logging setup instead of uvicorn's.
    uvicorn.run(app, host=bind_host, port=bind_port, log_config=None)


@ui.command()
@click.option(
    "--symbols",
    default="BTCUSDT,ETHUSDT,SOLUSDT",
    show_default=True,
    help="Comma-separated symbols to simulate",
)
@click.option("--seconds-per-candle", type=float, default=15.0, show_default=True)
@click.pass_context
def demo(ctx: click.Context, symbols: str, seconds_per_candle: float) -> None:
    """Publish synthetic events so the dashboard can be tried without trading.

    They share the trader's streams; delete kt:ui:events and kt:ui:ticks after.
    """
    app_config: AppConfig = ctx.obj["app_config"]
    redis = _redis_client(app_config, socket_timeout_s=5)
    feed = UiDemoFeed(
        publisher=RedisUiPublisher(redis, app_config.ui),
        symbols=[s.strip().upper() for s in symbols.split(",") if s.strip()],
        seconds_per_candle=seconds_per_candle,
    )
    click.echo("Publishing demo events, Ctrl+C to stop")
    try:
        asyncio.run(feed.run())
    except KeyboardInterrupt:
        click.echo("Demo feed stopped")


@ui.command("export-schema")
def export_schema() -> None:
    """Regenerate the JSON Schema the frontend builds its TS types from."""
    UI_SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_SCHEMA_PATH.write_text(render_ui_schema(), encoding="utf-8")
    click.echo(f"Wrote {UI_SCHEMA_PATH}")
