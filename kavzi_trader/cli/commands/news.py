import asyncio
from datetime import datetime
from pathlib import Path

import click
import httpx2

from kavzi_trader.news.coin_tagger import CoinTagger
from kavzi_trader.news.cointelegraph_backfill import CointelegraphBackfill
from kavzi_trader.news.news_feeds import NEWS_FEEDS
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.news.polite_fetcher import PoliteFetcher
from kavzi_trader.news.rss_collector import RssCollector
from kavzi_trader.news.rss_parser import RssParser
from kavzi_trader.news.theblock_backfill import TheBlockBackfill

_TIMEOUT_S = 30.0
# bitcoinmagazine.com's robots.txt asks for a 5 s crawl delay.
HOST_INTERVAL_S = {"bitcoinmagazine.com": 5.0}

_ROOT_OPTION = click.option(
    "--root",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/news"),
    show_default=True,
)


@click.group("news")
def news_group() -> None:
    """Collect crypto headlines into a point-in-time store."""


@news_group.command("collect")
@_ROOT_OPTION
def collect_command(root: Path) -> None:
    """Fetch the outlet RSS feeds once; run hourly, feeds hold only 1-4 days."""

    async def _job() -> dict[str, int]:
        async with httpx2.AsyncClient(timeout=_TIMEOUT_S) as http:
            fetcher = PoliteFetcher(http, host_interval_s=HOST_INTERVAL_S)
            collector = RssCollector(fetcher, RssParser(CoinTagger()), NewsStore(root))
            return await collector.collect(NEWS_FEEDS)

    added = asyncio.run(_job())
    failed = [source for source, n in added.items() if n < 0]
    summary = ", ".join(f"{s} {n}" for s, n in added.items() if n >= 0)
    click.echo(f"New headlines: {summary}")
    if failed:
        raise click.ClickException(f"feeds failed: {', '.join(failed)}")


@news_group.command("backfill")
@click.option("--from", "start", type=click.DateTime(formats=["%Y-%m"]), required=True)
@click.option("--to", "end", type=click.DateTime(formats=["%Y-%m"]), required=True)
@_ROOT_OPTION
def backfill_command(start: datetime, end: datetime, root: Path) -> None:
    """Fill past months from Cointelegraph and The Block sitemaps (inclusive).

    Slow by design (one request every 2 s); rerunning skips stored articles.
    """
    months = month_labels(start, end)

    async def _job() -> tuple[int, int]:
        async with httpx2.AsyncClient(timeout=_TIMEOUT_S) as http:
            fetcher = PoliteFetcher(http)
            store = NewsStore(root)
            tagger = CoinTagger()
            block = await TheBlockBackfill(fetcher, tagger, store).run(
                f"{months[0]}-01", f"{months[-1]}-31"
            )
            telegraph = await CointelegraphBackfill(fetcher, tagger, store).run(months)
            return block, telegraph

    block, telegraph = asyncio.run(_job())
    click.echo(
        f"Backfilled {', '.join(months)}: theblock {block}, cointelegraph {telegraph}"
    )


def month_labels(start: datetime, end: datetime) -> list[str]:
    """``YYYY-MM`` labels from ``start`` to ``end``, both inclusive."""
    if end < start:
        msg = f"--to {end:%Y-%m} is before --from {start:%Y-%m}"
        raise click.BadParameter(msg)
    first = start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    return [f"{i // 12}-{i % 12 + 1:02d}" for i in range(first, last + 1)]
