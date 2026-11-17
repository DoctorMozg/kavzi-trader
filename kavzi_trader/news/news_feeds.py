from pydantic import BaseModel, ConfigDict


class NewsFeedSchema(BaseModel):
    """An outlet RSS feed; robots.txt of each host allowed it on 2026-11-17."""

    model_config = ConfigDict(frozen=True)

    source: str
    url: str


NEWS_FEEDS: tuple[NewsFeedSchema, ...] = (
    NewsFeedSchema(
        source="coindesk", url="https://www.coindesk.com/arc/outboundfeeds/rss"
    ),
    NewsFeedSchema(source="cointelegraph", url="https://cointelegraph.com/rss"),
    NewsFeedSchema(source="theblock", url="https://www.theblock.co/rss.xml"),
    NewsFeedSchema(source="decrypt", url="https://decrypt.co/feed"),
    NewsFeedSchema(source="bitcoinmagazine", url="https://bitcoinmagazine.com/feed"),
)
