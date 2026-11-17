import asyncio
from pathlib import Path

import click
import httpx2

from kavzi_trader.news.coin_tagger import CoinTagger
from kavzi_trader.news.news_feeds import NEWS_FEEDS
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.news.polite_fetcher import PoliteFetcher
from kavzi_trader.news.rss_collector import RssCollector
from kavzi_trader.news.rss_parser import RssParser

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
