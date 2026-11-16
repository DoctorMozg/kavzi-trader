import asyncio
from datetime import UTC, datetime
from pathlib import Path

import click
import httpx2

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_downloader import ArchiveDownloader
from kavzi_trader.archive.archive_listing import ArchiveListing
from kavzi_trader.archive.archive_store import ArchiveStore
from kavzi_trader.archive.point_in_time_universe import PointInTimeUniverse
from kavzi_trader.config import AppConfig

_TIMEOUT_S = 120.0
UNIVERSE_FILE = "universe.parquet"


@click.command("archive")
@click.option(
    "--dataset",
    "datasets",
    type=click.Choice(sorted(ARCHIVE_DATASETS)),
    multiple=True,
    help="Datasets to mirror; all of them when not given.",
)
@click.option(
    "--symbols",
    default=None,
    help="Comma-separated; trading.symbols from the config when not given.",
)
@click.option(
    "--from-month",
    type=click.DateTime(formats=["%Y-%m"]),
    default="2020-01",
    show_default=True,
)
@click.option(
    "--root",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/archive"),
    show_default=True,
)
@click.pass_context
def archive_command(
    ctx: click.Context,
    datasets: tuple[str, ...],
    symbols: str | None,
    from_month: datetime,
    root: Path,
) -> None:
    """Mirror data.binance.vision USD-M archives into monthly Parquet files.

    Months already stored are skipped, so a rerun resumes an interrupted
    mirror and picks up newly published months.
    """
    app_config: AppConfig = ctx.obj["app_config"]
    names = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else app_config.trading.symbols
    )
    chosen = [ARCHIVE_DATASETS[d] for d in datasets or sorted(ARCHIVE_DATASETS)]
    store = ArchiveStore(root)
    first_month = from_month.strftime("%Y-%m")

    async def _job() -> None:
        async with httpx2.AsyncClient(timeout=_TIMEOUT_S) as http:
            current_month = datetime.now(UTC).strftime("%Y-%m")
            downloader = ArchiveDownloader(
                http, ArchiveListing(http), store, current_month
            )
            fetched = skipped = 0
            for symbol in names:
                for dataset in chosen:
                    done = await downloader.sync(dataset, symbol, first_month)
                    fetched += done.fetched
                    skipped += done.skipped
        click.echo(
            f"{len(names)} symbols: {fetched} months fetched, "
            f"{skipped} already stored, under {root}"
        )

    asyncio.run(_job())
    if ARCHIVE_DATASETS["klines"] in chosen:
        universe = PointInTimeUniverse.from_store(store)
        universe.save(root / UNIVERSE_FILE)
        click.echo(f"Universe of {len(universe)} symbols: {root / UNIVERSE_FILE}")
