import time
from unittest.mock import patch

from kavzi_trader.external.circuit_breaker import CircuitBreaker, CircuitBreakerState


def test_starts_closed() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.should_allow() is True


def test_stays_closed_below_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.should_allow() is True


def test_opens_at_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.should_allow() is False


def test_half_open_after_cooldown() -> None:
    cb = CircuitBreaker(failure_threshold=2, cooldown_s=1.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

    # Simulate cooldown elapsed
    cb._opened_at = time.monotonic() - 2.0
    assert cb.should_allow() is True
    assert cb.state == CircuitBreakerState.HALF_OPEN


def test_half_open_success_closes() -> None:
    cb = CircuitBreaker(failure_threshold=2, cooldown_s=0.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

    # Trigger half-open (zero cooldown)
    cb.should_allow()
    assert cb.state == CircuitBreakerState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.should_allow() is True


def test_half_open_failure_reopens_with_doubled_cooldown() -> None:
    cb = CircuitBreaker(
        failure_threshold=2,
        cooldown_s=10.0,
        max_cooldown_s=100.0,
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

    # Force half-open
    cb._opened_at = time.monotonic() - 20.0
    cb.should_allow()
    assert cb.state == CircuitBreakerState.HALF_OPEN

    # Probe fails → re-open with doubled cooldown
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    assert cb._current_cooldown_s == 20.0  # noqa: SLF001


def test_cooldown_capped_at_max() -> None:
    cb = CircuitBreaker(
        failure_threshold=1,
        cooldown_s=500.0,
        max_cooldown_s=600.0,
    )
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

    # Force half-open and fail again
    cb._opened_at = time.monotonic() - 600.0
    cb.should_allow()
    cb.record_failure()
    # 500 * 2 = 1000, but max is 600
    assert cb._current_cooldown_s == 600.0  # noqa: SLF001


def test_success_resets_failure_count() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    # After reset, need 3 more failures to open
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.CLOSED


def test_open_blocks_until_cooldown() -> None:
    cb = CircuitBreaker(failure_threshold=1, cooldown_s=999.0)
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.should_allow() is False
    assert cb.should_allow() is False
