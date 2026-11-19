from datetime import UTC, datetime
from pathlib import Path

import click

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.cli.commands.eval_options import (
    INTERVAL_CHOICE,
    MS_PER_S,
    S_PER_MIN,
    SYMBOLS_OPTION,
    day_start_ms,
)
from kavzi_trader.cli.commands.market_data_loader import MarketDataLoader
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.dataset_builder import DAYS_PER_MONTH, MS_PER_DAY
from kavzi_trader.evals.kline_downloader import KlineDownloader
from kavzi_trader.order_flow.calculator import OrderFlowCalculator


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / MS_PER_S, UTC).date().isoformat()


@click.command("refresh-cache")
@click.option(
    "--interval",
    type=INTERVAL_CHOICE,
    default=None,
    help="Candle interval; default the trading interval.",
)
@click.option(
    "--months",
    type=click.FloatRange(min=0, min_open=True),
    default=12.0,
    show_default=True,
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.option(
    "--metrics/--no-metrics",
    default=False,
    help="Also fill the 5-minute metrics archive (OI and long/short ratios).",
)
@SYMBOLS_OPTION
@click.pass_context
def refresh_cache_command(
    ctx: click.Context,
    interval: str | None,
    months: float,
    cache_dir: Path,
    metrics: bool,
    symbols: list[str] | None,
) -> None:
    """Fill cached candles, funding and OI up to today; the dataset is untouched."""
    app_config: AppConfig = ctx.obj["app_config"]
    interval = interval or app_config.trading.interval
    end_ms = day_start_ms(None)
    start_ms = end_ms - int(months * DAYS_PER_MONTH * MS_PER_DAY)
    cache = CandleCache(cache_dir, interval)
    symbols = symbols or app_config.trading.symbols

    async def _job(exchange: ExchangeClient) -> None:
        downloader = KlineDownloader(exchange, cache, interval)
        for symbol in symbols:
            await downloader.ensure_range(symbol, start_ms, end_ms)

    loader = MarketDataLoader(cache_dir, ctx.obj.get("exchange_client"))
    loader.run(_job)
    frames = {s: cache.load(s) for s in symbols}
    frames = {s: f for s, f in frames.items() if not f.empty}
    settlements = loader.funding(frames)
    period = OrderFlowCalculator(KLINE_INTERVALS[interval] // S_PER_MIN).oi_period
    snapshots = loader.oi(frames, period)
    archive = loader.metrics(frames) if metrics else {}
    for symbol, frame in frames.items():
        first, last = frame["open_time_ms"].iloc[[0, -1]]
        line = (
            f"{symbol}: {len(frame)} {interval} candles {_day(first)} to "
            f"{_day(last)}, {len(settlements[symbol])} funding, "
            f"{len(snapshots[symbol])} OI {period}"
        )
        if metrics:
            line += f", {len(archive[symbol])} metrics 5m"
        click.echo(line)
