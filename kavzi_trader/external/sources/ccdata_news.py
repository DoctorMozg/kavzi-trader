import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.schemas import CCDataNewsDataSchema

logger = logging.getLogger(__name__)

_CCDATA_NEWS_URL = "https://data-api.ccdata.io/news/v1/article/list"
_TIMEOUT_S = 10.0


class CCDataNewsSource(ExternalSource):
    """Fetches news sentiment from CCData (CryptoCompare successor) API.

    No API key required. Each article includes a pre-computed SENTIMENT
    field (POSITIVE/NEGATIVE/NEUTRAL) which we aggregate into counts.
    """

    def __init__(
        self,
        max_results: int = 20,
        max_headlines: int = 5,
    ) -> None:
        self._max_results = max_results
        self._max_headlines = max_headlines
        self._client = httpx.AsyncClient(timeout=_TIMEOUT_S)

    @property
    def name(self) -> str:
        return "ccdata_news"

    async def fetch(self) -> CCDataNewsDataSchema | None:
        logger.info("Fetching CCData news sentiment")
        try:
            resp = await self._client.get(
                _CCDATA_NEWS_URL,
                params={
                    "lang": "EN",
                    "categories": "BTC,ETH",
                    "limit": self._max_results,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            articles: list[dict[str, object]] = body.get("Data", [])
        except Exception:
            logger.exception("CCData news fetch failed")
            return None
        else:
            result = self._parse_articles(articles)
            logger.info(
                "CCData news fetched: articles=%d bullish=%d bearish=%d "
                "neutral=%d score=%.2f",
                len(articles),
                result.bullish_count,
                result.bearish_count,
                result.neutral_count,
                result.sentiment_score,
                extra={
                    "articles_count": len(articles),
                    "bullish": result.bullish_count,
                    "bearish": result.bearish_count,
                    "sentiment_score": float(result.sentiment_score),
                },
            )
            return result

    def _parse_articles(
        self,
        articles: list[dict[str, object]],
    ) -> CCDataNewsDataSchema:
        bullish = 0
        bearish = 0
        neutral = 0
        headlines: list[str] = []

        for article in articles:
            title = str(article.get("TITLE", ""))
            if title:
                headlines.append(title)

            sentiment = str(article.get("SENTIMENT", "NEUTRAL")).upper()
            if sentiment == "POSITIVE":
                bullish += 1
            elif sentiment == "NEGATIVE":
                bearish += 1
            else:
                neutral += 1

        total = max(len(articles), 1)
        score = Decimal(str((bullish - bearish) / total))

        return CCDataNewsDataSchema(
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            top_headlines=headlines[: self._max_headlines],
            sentiment_score=score,
            fetched_at=datetime.now(UTC),
        )
