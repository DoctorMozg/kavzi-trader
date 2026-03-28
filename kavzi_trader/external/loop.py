import asyncio
import logging
import time
from typing import Protocol

from pydantic import BaseModel

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.external.schemas import (
    CryptoPanicDataSchema,
    DeribitDvolDataSchema,
    ExternalDataSnapshotSchema,
    FearGreedDataSchema,
    SentimentSummarySchema,
)

logger = logging.getLogger(__name__)


class SentimentSynthesizerProtocol(Protocol):
    async def synthesize(
        self,
        snapshot: ExternalDataSnapshotSchema,
    ) -> SentimentSummarySchema | None: ...


class ExternalSentimentLoop:
    """Combined fetch + synthesize loop.

    Each cycle:
    1. Fetch all sources in parallel via asyncio.gather
    2. Build snapshot and store in cache
    3. Synthesize via LLM and store summary in cache
    """

    def __init__(
        self,
        sources: list[ExternalSource],
        synthesizer: SentimentSynthesizerProtocol | None,
        cache: ExternalDataCache,
        interval_s: int = 300,
    ) -> None:
        self._sources = sources
        self._synthesizer = synthesizer
        self._cache = cache
        self._interval_s = interval_s

    async def warm_up(self) -> None:
        """Run a single fetch+synthesize cycle before the main loop starts."""
        logger.info("ExternalSentimentLoop warming up (pre-fetching all sources)")
        await self._cycle()
        logger.info("ExternalSentimentLoop warm-up complete")

    async def run(self) -> None:
        logger.info(
            "ExternalSentimentLoop started with %d sources, interval=%ds",
            len(self._sources),
            self._interval_s,
        )
        while True:
            await self._cycle()
            await asyncio.sleep(self._interval_s)

    async def _cycle(self) -> None:
        t0 = time.monotonic()

        # 1. Fetch all sources in parallel
        snapshot = await self._fetch_all()
        self._cache.set_snapshot(snapshot)

        # 2. Synthesize if enabled
        if self._synthesizer is not None and not snapshot.is_empty():
            try:
                summary = await self._synthesizer.synthesize(snapshot)
                if summary is not None:
                    self._cache.set_sentiment_summary(summary)
            except Exception:
                logger.exception("Sentiment synthesis failed, keeping stale summary")
        elif snapshot.is_empty():
            logger.debug("All external sources returned None, skipping synthesis")

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "ExternalSentimentLoop cycle complete in %.1fms",
            elapsed_ms,
            extra={"elapsed_ms": round(elapsed_ms, 1)},
        )

    async def _fetch_all(self) -> ExternalDataSnapshotSchema:
        results = await asyncio.gather(
            *(self._fetch_one(source) for source in self._sources),
            return_exceptions=True,
        )

        source_data: dict[str, BaseModel] = {}
        for source, result in zip(self._sources, results, strict=True):
            if isinstance(result, BaseException):
                logger.exception(
                    "External source %s raised an exception",
                    source.name,
                    exc_info=result,
                )
            elif result is not None:
                source_data[source.name] = result

        fetched = sorted(source_data.keys())
        failed = sorted(
            source.name
            for source, result in zip(self._sources, results, strict=True)
            if isinstance(result, BaseException) or result is None
        )
        logger.info(
            "External fetch complete: ok=%s failed=%s",
            fetched or "none",
            failed or "none",
            extra={"fetched": fetched, "failed": failed},
        )

        return ExternalDataSnapshotSchema(
            deribit_dvol=self._typed_get(
                source_data, "deribit_dvol", DeribitDvolDataSchema
            ),
            fear_greed=self._typed_get(source_data, "fear_greed", FearGreedDataSchema),
            cryptopanic=self._typed_get(
                source_data, "cryptopanic", CryptoPanicDataSchema
            ),
        )

    async def _fetch_one(self, source: ExternalSource) -> BaseModel | None:
        try:
            return await source.fetch()
        except Exception:
            logger.exception(
                "External source %s fetch failed",
                source.name,
            )
            return None

    @staticmethod
    def _typed_get[T: BaseModel](
        data: dict[str, BaseModel],
        key: str,
        expected_type: type[T],
    ) -> T | None:
        value = data.get(key)
        if value is None:
            return None
        if isinstance(value, expected_type):
            return value
        return None
