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
        self._elevated_fear_threshold = config.fgi_elevated_fear_threshold
        self._elevated_fear_confluence_min = config.fgi_elevated_fear_confluence_min
        self._elevated_greed_threshold = config.fgi_elevated_greed_threshold
        self._elevated_greed_confluence_min = config.fgi_elevated_greed_confluence_min

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

    def get_confluence_override(self, direction: str) -> int | None:
        """Return a raised confluence gate when sentiment opposes the trade.

        Directional: LONGs are tightened in the elevated-fear zone
        (extreme_fear, elevated_fear] and SHORTs in the elevated-greed zone
        [elevated_greed, extreme_greed) — the directions that historically
        chased sentiment into losses. The opposing direction (e.g. a SHORT in
        fear) is left untouched. Returns None when nothing applies.
        """
        snapshot = self._cache.get_snapshot()
        fgi = snapshot.fear_greed
        if fgi is None:
            return None
        value = fgi.value
        if (
            direction == "LONG"
            and self._fear_threshold < value <= self._elevated_fear_threshold
        ):
            return self._elevated_fear_confluence_min
        if (
            direction == "SHORT"
            and self._elevated_greed_threshold <= value < self._greed_threshold
        ):
            return self._elevated_greed_confluence_min
        return None
