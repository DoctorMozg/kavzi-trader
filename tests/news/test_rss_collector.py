from pathlib import Path

import httpx2

from kavzi_trader.news.coin_tagger import CoinTagger
from kavzi_trader.news.news_feeds import NewsFeedSchema
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.news.polite_fetcher import USER_AGENT, PoliteFetcher
from kavzi_trader.news.rss_collector import RssCollector
from kavzi_trader.news.rss_parser import RssParser
from tests.news.conftest import rss

FEEDS = (
    NewsFeedSchema(source="up", url="https://up.io/rss"),
    NewsFeedSchema(source="down", url="https://down.io/rss"),
)


async def test_a_failing_feed_does_not_stop_the_others(tmp_path: Path) -> None:
    agents: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        agents.append(request.headers["User-Agent"])
        if request.url.host == "down.io":
            return httpx2.Response(503)
        return httpx2.Response(
            200,
            text=rss(
                ("Ether rallies", "https://up.io/1", "Tue, 17 Nov 2026 09:00:00 GMT")
            ),
        )

    store = NewsStore(tmp_path)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        collector = RssCollector(
            PoliteFetcher(http, min_interval_s=0), RssParser(CoinTagger()), store
        )
        added = await collector.collect(FEEDS)

    assert added == {"up": 1, "down": -1}
    assert len(store) == 1
    assert agents == [USER_AGENT, USER_AGENT]
