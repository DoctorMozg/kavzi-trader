import logging

from kavzi_trader.external.cache import ExternalDataCache
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema

logger = logging.getLogger(__name__)


class FearGreedGateFilter:
    """Market-wide circuit breaker based on FGI extreme values.

    Blocks ALL trades when FGI is at extreme fear (<=10) or extreme greed (>=90).
    Fails open: if FGI data is unavailable, trading continues.
    """

    def __init__(
        self,
        external_cache: ExternalDataCache,
        config: FilterConfigSchema,
    ) -> None:
        self._cache = external_cache
        self._fear_threshold = config.fgi_extreme_fear_threshold
        self._greed_threshold = config.fgi_extreme_greed_threshold

    def evaluate(self) -> FilterResultSchema:
        snapshot = self._cache.get_snapshot()
        fgi = snapshot.fear_greed

        if fgi is None:
            logger.debug("FGI gate: no data available, fail-open")
            return FilterResultSchema(
                name="fear_greed_gate",
                is_allowed=True,
                reason="FGI unavailable (fail-open)",
            )

        value = fgi.value

        if value <= self._fear_threshold:
            logger.info(
                "FGI gate BLOCKED: extreme fear FGI=%d (<=%d)",
                value,
                self._fear_threshold,
                extra={"fgi_value": value},
            )
            return FilterResultSchema(
                name="fear_greed_gate",
                is_allowed=False,
                reason=f"Extreme fear: FGI={value} (<={self._fear_threshold})",
            )

        if value >= self._greed_threshold:
            logger.info(
                "FGI gate BLOCKED: extreme greed FGI=%d (>=%d)",
                value,
                self._greed_threshold,
                extra={"fgi_value": value},
            )
            return FilterResultSchema(
                name="fear_greed_gate",
                is_allowed=False,
                reason=f"Extreme greed: FGI={value} (>={self._greed_threshold})",
            )

        logger.debug(
            "FGI gate PASSED: FGI=%d",
            value,
            extra={"fgi_value": value},
        )
        return FilterResultSchema(
            name="fear_greed_gate",
            is_allowed=True,
            reason=f"FGI={value} (normal range)",
        )
