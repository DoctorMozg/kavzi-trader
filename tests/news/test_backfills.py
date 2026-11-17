from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
import httpx2
import pytest

from kavzi_trader.cli.commands.news import month_labels
from kavzi_trader.news.coin_tagger import CoinTagger
from kavzi_trader.news.cointelegraph_backfill import CointelegraphBackfill
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.news.polite_fetcher import PoliteFetcher
from kavzi_trader.news.theblock_backfill import INDEX_URL, TheBlockBackfill

AS_OF = datetime(2026, 7, 17, tzinfo=UTC)
WINDOW = timedelta(days=5)
LAG = timedelta(hours=2)


def _sitemap(*urls: str) -> str:
    return (
        "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"
    )


def _page(published: str, title: str) -> str:
    return (
        f'<meta property="og:title" content="{title}">'
        f'<script type="application/ld+json">{{"datePublished":"{published}"}}</script>'
    )


async def _run(pages: dict[str, httpx2.Response], job):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return pages.get(str(request.url), httpx2.Response(404))

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        return await job(PoliteFetcher(http, min_interval_s=0))


class TestCointelegraphBackfill:
    async def test_stores_exact_publish_time_and_skips_broken_pages(
        self, tmp_path: Path
    ) -> None:
        ok, broken = (
            "https://cointelegraph.com/news/a",
            "https://cointelegraph.com/news/b",
        )
        pages = {
            "https://cointelegraph.com/sitemap/articles/2026-07.xml": httpx2.Response(
                200, text=_sitemap(ok, broken)
            ),
            ok: httpx2.Response(
                200, text=_page("2026-07-16T08:27:31.863Z", "Solana &amp; XRP rally")
            ),
            broken: httpx2.Response(200, text="<html>no metadata</html>"),
        }
        store = NewsStore(tmp_path)

        added = await _run(
            pages,
            lambda f: CointelegraphBackfill(f, CoinTagger(), store).run(["2026-07"]),
        )

        assert added == 1
        [item] = store.query(AS_OF, WINDOW, LAG)
        assert item.title == "Solana & XRP rally"
        assert item.coins == ("SOL", "XRP")
        assert item.published_at == datetime(2026, 7, 16, 8, 27, 31, 863000, tzinfo=UTC)


class TestTheBlockBackfill:
    async def test_keeps_dated_urls_in_range_at_day_precision(
        self, tmp_path: Path
    ) -> None:
        chunk = "https://www.theblock.co/sitemap_tbco_post_type_post_27.xml"
        inside = "https://www.theblock.co/news/markets/2026-07-15-bitcoin-etf-flows-turn-positive-361234"
        pages = {
            INDEX_URL: httpx2.Response(200, text=_sitemap(chunk)),
            chunk: httpx2.Response(
                200,
                text=_sitemap(
                    inside,
                    inside,
                    "https://www.theblock.co/news/markets/2026-06-30-older-story-350000",
                    "https://www.theblock.co/post/123/undated",
                ),
            ),
        }
        store = NewsStore(tmp_path)

        added = await _run(
            pages,
            lambda f: TheBlockBackfill(f, CoinTagger(), store).run(
                "2026-07-01", "2026-10-31"
            ),
        )

        assert added == 1
        [item] = store.query(AS_OF, WINDOW, LAG)
        assert item.title == "Bitcoin etf flows turn positive"
        assert item.precision == "day"
        assert item.coins == ("BTC",)


class TestMonthLabels:
    def test_spans_a_year_boundary_inclusively(self) -> None:
        labels = month_labels(datetime(2026, 11, 1), datetime(2027, 2, 1))  # noqa: DTZ001

        assert labels == ["2026-11", "2026-12", "2027-01", "2027-02"]

    def test_rejects_a_reversed_range(self) -> None:
        with pytest.raises(click.BadParameter, match="before"):
            month_labels(datetime(2026, 9, 1), datetime(2026, 7, 1))  # noqa: DTZ001
