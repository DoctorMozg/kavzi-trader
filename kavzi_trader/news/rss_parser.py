import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from kavzi_trader.news.coin_tagger import CoinTagger
from kavzi_trader.news.news_item_schema import NewsItemSchema

logger = logging.getLogger(__name__)


class RssParser:
    """Turns an RSS 2.0 document into news items stamped with their pubDate."""

    def __init__(self, tagger: CoinTagger) -> None:
        self._tagger = tagger

    def parse(
        self, xml_text: str, source: str, seen_at: datetime
    ) -> list[NewsItemSchema]:
        # expat >= 2.4 caps entity expansion and ElementTree never fetches
        # external entities, so stdlib parsing is safe for feed XML.
        root = ET.fromstring(xml_text)  # noqa: S314
        items: list[NewsItemSchema] = []
        for node in root.findall("./channel/item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or node.findtext("guid") or "").strip()
            stamp = node.findtext("pubDate")
            if not title or not link or not stamp:
                logger.debug("Skipping %s item without title, link or pubDate", source)
                continue
            categories = [c.text for c in node.findall("category") if c.text]
            items.append(
                NewsItemSchema(
                    url=link,
                    title=title,
                    source=source,
                    published_at=parsedate_to_datetime(stamp).astimezone(UTC),
                    precision="exact",
                    first_seen_at=seen_at,
                    coins=self._tagger.tag([title, *categories]),
                )
            )
        return items
