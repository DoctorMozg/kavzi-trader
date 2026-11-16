import asyncio
from datetime import datetime
from pathlib import Path

import click
import httpx2

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS
from kavzi_trader.archive.archive_downloader import ArchiveDownloader
from kavzi_trader.archive.archive_listing import ArchiveListing
from kavzi_trader.archive.archive_store import ArchiveStore

_TIMEOUT_S = 120.0


def is_usdt_perpetual(symbol: str) -> bool:
    """Dated quarterlies carry an _YYMMDD suffix; USDC-margined ones end in USDC."""
    return symbol.endswith("USDT") and "_" not in symbol


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
    help="Comma-separated; every USDT perpetual ever listed when not given.",
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
def archive_command(
    datasets: tuple[str, ...],
    symbols: str | None,
    from_month: datetime,
    root: Path,
) -> None:
    """Mirror data.binance.vision monthly USD-M archives into Parquet.

    Delisted symbols are included. Months already stored are skipped, so a
    rerun resumes an interrupted mirror and picks up newly published months.
    """
    chosen = [ARCHIVE_DATASETS[d] for d in datasets or sorted(ARCHIVE_DATASETS)]
    store = ArchiveStore(root)
    first_month = from_month.strftime("%Y-%m")

    async def _job() -> tuple[int, int]:
        async with httpx2.AsyncClient(timeout=_TIMEOUT_S) as http:
            listing = ArchiveListing(http)
            names = (
                [s.strip().upper() for s in symbols.split(",") if s.strip()]
                if symbols
                else [
                    s
                    for s in await listing.symbols(ARCHIVE_DATASETS["klines"].name)
                    if is_usdt_perpetual(s)
                ]
            )
            downloader = ArchiveDownloader(http, listing, store)
            fetched = skipped = 0
            for symbol in names:
                for dataset in chosen:
                    done = await downloader.sync(dataset, symbol, first_month)
                    fetched += done.fetched
                    skipped += done.skipped
            click.echo(f"{len(names)} symbols")
            return fetched, skipped

    fetched, skipped = asyncio.run(_job())
    click.echo(f"{fetched} months fetched, {skipped} already stored, under {root}")
