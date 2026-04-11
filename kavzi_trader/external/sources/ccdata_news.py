import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.schemas import CCDataNewsDataSchema

logger = logging.getLogger(__name__)

_CCDATA_NEWS_URL = "https://data-api.ccdata.io/news/v1/article/list"
_TIMEOUT_S = 10.0
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE_S = 1.0


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
        articles = await self._fetch_articles_with_retry()
        if articles is None:
            return None

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

    async def _fetch_articles_with_retry(self) -> list[dict[str, object]] | None:
        """Fetch raw article list with bounded retries.

        Transient network / 5xx errors are retried with exponential
        backoff (1s, 2s, 4s) up to `_MAX_RETRIES` attempts. Intermediate
        failures are logged as warnings; the final failure is logged
        once as an exception and `None` is returned so the caller's
        graceful-degradation path (stale cache + circuit breaker in
        `external/loop.py`) can take over.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
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
            except Exception as exc:
                if attempt < _MAX_RETRIES:
                    backoff_s = _RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1))
                    logger.warning(
                        "CCData news fetch attempt %d/%d failed: %s; retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        backoff_s,
                    )
                    await asyncio.sleep(backoff_s)
                    continue
                logger.exception("CCData news fetch failed after %d attempts", attempt)
                return None
            else:
                return articles
        return None

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
