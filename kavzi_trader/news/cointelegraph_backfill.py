import html
import logging
import re
from datetime import UTC, datetime

import httpx2

from kavzi_trader.news.coin_tagger import CoinTagger
from kavzi_trader.news.news_item_schema import NewsItemSchema
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.news.polite_fetcher import PoliteFetcher

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://cointelegraph.com/sitemap/articles/{month}.xml"
_LOC = re.compile(r"<loc>([^<]+)</loc>")
_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_TITLE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"')


class CointelegraphBackfill:
    """Past Cointelegraph headlines: monthly sitemap, then each page's publish time.

    Titles are the page as it reads today, which may differ from the original.
    """

    def __init__(
        self, fetcher: PoliteFetcher, tagger: CoinTagger, store: NewsStore
    ) -> None:
        self._fetcher = fetcher
        self._tagger = tagger
        self._store = store

    async def run(self, months: list[str]) -> int:
        """Stores every article of the given ``YYYY-MM`` months not yet stored."""
        added = failed = 0
        for month in months:
            sitemap = await self._fetcher.get_text(SITEMAP_URL.format(month=month))
            urls = [u for u in _LOC.findall(sitemap) if u not in self._store]
            logger.info("Cointelegraph %s: %d articles to fetch", month, len(urls))
            for url in urls:
                try:
                    item = self._item(url, await self._fetcher.get_text(url))
                except httpx2.HTTPError, ValueError:
                    logger.exception("Cointelegraph article failed: %s", url)
                    failed += 1
                    continue
                added += self._store.add([item])
        logger.info("Cointelegraph backfill: %d added, %d failed", added, failed)
        return added

    def _item(self, url: str, page: str) -> NewsItemSchema:
        published = _PUBLISHED.search(page)
        title = _TITLE.search(page)
        if published is None or title is None:
            msg = f"no datePublished or og:title in {url}"
            raise ValueError(msg)
        headline = html.unescape(title.group(1))
        return NewsItemSchema(
            url=url,
            title=headline,
            source="cointelegraph",
            published_at=datetime.fromisoformat(published.group(1)).astimezone(UTC),
            precision="exact",
            first_seen_at=datetime.now(UTC),
            coins=self._tagger.tag([headline]),
        )
