import logging
from datetime import UTC, datetime

from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime

logger = logging.getLogger(__name__)


class StalenessChecker:
    """Evaluates decision staleness using volatility-aware thresholds."""

    def __init__(self, config: ExecutionConfigSchema) -> None:
        self._config = config

    def is_stale(
        self,
        created_at_ms: int,
        regime: VolatilityRegime,
        now: datetime | None = None,
    ) -> bool:
        now_dt = now or datetime.now(UTC)
        now_ms = int(now_dt.timestamp() * 1000)
        age_ms = now_ms - created_at_ms

        # Fail closed on inconsistent time: a negative age means our clock and
        # the decision origin's clock disagree. Either clock could be wrong,
        # and executing in that state is riskier than skipping.
        if age_ms < 0:
            logger.warning(
                "Decision age is negative (%dms) — treating as stale (clock skew?)",
                age_ms,
            )
            return True

        threshold = self._threshold_ms(regime)
        stale = age_ms > threshold
        logger.debug(
            "Staleness check: age_ms=%d threshold_ms=%d regime=%s stale=%s",
            age_ms,
            threshold,
            regime.value,
            stale,
        )
        return stale

    def _threshold_ms(self, regime: VolatilityRegime) -> int:
        return self._config.staleness_thresholds_ms.get(
            regime.value,
            self._config.staleness_thresholds_ms[VolatilityRegime.NORMAL.value],
        )
