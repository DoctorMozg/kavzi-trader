import logging
import re
from datetime import UTC, datetime

from kavzi_trader.news.coin_tagger import CoinTagger
from kavzi_trader.news.news_item_schema import NewsItemSchema
from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.news.polite_fetcher import PoliteFetcher

logger = logging.getLogger(__name__)

INDEX_URL = "https://www.theblock.co/sitemap_tbco_index.xml"
_POST_SITEMAP = re.compile(r"<loc>([^<]*sitemap_tbco_post_type_post_\d+\.xml)</loc>")
_LOC = re.compile(r"<loc>([^<]+)</loc>")
# Article URLs end in /<yyyy-mm-dd>-<slug>[-<id>].
_DATED_SLUG = re.compile(r"/(\d{4}-\d{2}-\d{2})-([a-z0-9-]+?)(?:-\d+)?/?$")


class TheBlockBackfill:
    """Past The Block headlines from sitemap URLs alone, at day precision.

    Article pages sit behind a bot challenge, so the title is the URL slug.
    """

    def __init__(
        self, fetcher: PoliteFetcher, tagger: CoinTagger, store: NewsStore
    ) -> None:
        self._fetcher = fetcher
        self._tagger = tagger
        self._store = store

    async def run(self, first_day: str, last_day: str) -> int:
        """Stores articles dated ``first_day`` to ``last_day`` (ISO, inclusive)."""
        index = await self._fetcher.get_text(INDEX_URL)
        items: list[NewsItemSchema] = []
        for sitemap_url in _POST_SITEMAP.findall(index):
            sitemap = await self._fetcher.get_text(sitemap_url)
            for url in _LOC.findall(sitemap):
                match = _DATED_SLUG.search(url)
                if match and first_day <= match.group(1) <= last_day:
                    items.append(self._item(url, match.group(1), match.group(2)))
        added = self._store.add(items)
        logger.info("The Block backfill: %d dated URLs, %d added", len(items), added)
        return added

    def _item(self, url: str, day: str, slug: str) -> NewsItemSchema:
        title = slug.replace("-", " ").capitalize()
        return NewsItemSchema(
            url=url,
            title=title,
            source="theblock",
            published_at=datetime.fromisoformat(day).replace(tzinfo=UTC),
            precision="day",
            first_seen_at=datetime.now(UTC),
            coins=self._tagger.tag([title]),
        )
