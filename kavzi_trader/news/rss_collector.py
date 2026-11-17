import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import httpx2

from kavzi_trader.news.news_feeds import NewsFeedSchema
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.news.polite_fetcher import PoliteFetcher
from kavzi_trader.news.rss_parser import RssParser

logger = logging.getLogger(__name__)


class RssCollector:
    """One pass over the outlet feeds; a failing feed doesn't stop the others."""

    def __init__(
        self, fetcher: PoliteFetcher, parser: RssParser, store: NewsStore
    ) -> None:
        self._fetcher = fetcher
        self._parser = parser
        self._store = store

    async def collect(self, feeds: tuple[NewsFeedSchema, ...]) -> dict[str, int]:
        """New headlines stored per source; -1 marks a feed that failed."""
        added: dict[str, int] = {}
        for feed in feeds:
            try:
                text = await self._fetcher.get_text(feed.url)
                items = self._parser.parse(text, feed.source, datetime.now(UTC))
            except httpx2.HTTPError, ET.ParseError:
                logger.exception("News feed %s failed: %s", feed.source, feed.url)
                added[feed.source] = -1
                continue
            added[feed.source] = self._store.add(items)
        return added
