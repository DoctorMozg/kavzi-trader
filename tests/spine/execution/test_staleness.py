from datetime import UTC, datetime

from kavzi_trader.spine.execution.config import ExecutionConfigSchema
from kavzi_trader.spine.execution.staleness import StalenessChecker
from kavzi_trader.spine.risk.schemas import VolatilityRegime


def test_staleness_checker_detects_expired() -> None:
    config = ExecutionConfigSchema(
        staleness_thresholds_ms={
            VolatilityRegime.NORMAL.value: 100,
            VolatilityRegime.LOW.value: 100,
            VolatilityRegime.HIGH.value: 100,
            VolatilityRegime.EXTREME.value: 100,
        },
    )
    checker = StalenessChecker(config)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    assert checker.is_stale(created_at_ms=0, regime=VolatilityRegime.NORMAL, now=now)


def test_staleness_checker_allows_recent() -> None:
    config = ExecutionConfigSchema()
    checker = StalenessChecker(config)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    assert not checker.is_stale(
        created_at_ms=int(now.timestamp() * 1000),
        regime=VolatilityRegime.NORMAL,
        now=now,
    )


def test_staleness_checker_treats_future_timestamp_as_stale() -> None:
    """Clock skew — decision from the 'future' must fail closed."""
    config = ExecutionConfigSchema()
    checker = StalenessChecker(config)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    now_ms = int(now.timestamp() * 1000)

    assert checker.is_stale(
        created_at_ms=now_ms + 1000,
        regime=VolatilityRegime.NORMAL,
        now=now,
    )
