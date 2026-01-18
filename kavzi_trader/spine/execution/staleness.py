from datetime import UTC, datetime

from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.risk.schemas import VolatilityRegime


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
        threshold = self._threshold_ms(regime)
        return (now_ms - created_at_ms) > threshold

    def _threshold_ms(self, regime: VolatilityRegime) -> int:
        return self._config.staleness_thresholds_ms.get(
            regime.value,
            self._config.staleness_thresholds_ms[VolatilityRegime.NORMAL.value],
        )
