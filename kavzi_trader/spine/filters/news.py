import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema
from kavzi_trader.spine.filters.news_event_schema import NewsEventSchema

logger = logging.getLogger(__name__)


class NewsEventFilter:
    """Blocks trades during configured windows around scheduled events."""

    def __init__(
        self,
        config: FilterConfigSchema,
        time_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self._config = config
        self._time_provider = time_provider

    def evaluate(
        self,
        events: list[NewsEventSchema] | None,
        current_time: datetime | None = None,
    ) -> FilterResultSchema:
        now = current_time or self._time_provider()
        if not events:
            logger.debug("News filter: no events scheduled, allowed")
            return FilterResultSchema(
                name="news",
                is_allowed=True,
                reason=None,
            )

        before = timedelta(minutes=self._config.news_block_before_min)
        after = timedelta(minutes=self._config.news_block_after_min)

        for event in events:
            window_start = event.start_time - before
            window_end = event.end_time + after
            if window_start <= now <= window_end:
                logger.debug(
                    "News filter: blocked by event=%s window=%s..%s",
                    event.name, window_start, window_end,
                )
                return FilterResultSchema(
                    name="news",
                    is_allowed=False,
                    reason=event.name,
                )

        logger.debug(
            "News filter: %d events checked, none active, allowed",
            len(events),
        )
        return FilterResultSchema(
            name="news",
            is_allowed=True,
            reason=None,
        )
