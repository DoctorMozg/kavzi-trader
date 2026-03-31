import time

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

    cb.record_success()  # type: ignore[unreachable]
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
    cb.record_failure()  # type: ignore[unreachable]
    assert cb.state == CircuitBreakerState.OPEN
    assert cb._current_cooldown_s == 20.0


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
    assert cb._current_cooldown_s == 600.0


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


def _cycle_to_half_open_and_fail(cb: CircuitBreaker) -> None:
    """Force OPEN→HALF_OPEN transition, then record a probe failure."""
    cb._opened_at = time.monotonic() - cb._current_cooldown_s - 1
    assert cb.should_allow() is True
    assert cb.state == CircuitBreakerState.HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN


def test_latches_open_after_max_reopen_count() -> None:
    """After max_reopen_count consecutive probe failures, breaker is latched."""
    cb = CircuitBreaker(
        failure_threshold=1,
        cooldown_s=1.0,
        max_cooldown_s=10.0,
        max_reopen_count=3,
    )
    cb.record_failure()  # CLOSED → OPEN
    assert cb.state == CircuitBreakerState.OPEN

    # Cycle 1: OPEN → HALF_OPEN → fail → OPEN
    _cycle_to_half_open_and_fail(cb)
    assert cb.should_allow() is False  # still in cooldown, not latched yet

    # Cycle 2
    _cycle_to_half_open_and_fail(cb)

    # Cycle 3 — should latch
    _cycle_to_half_open_and_fail(cb)

    # Latched: should_allow always returns False, even after cooldown
    cb._opened_at = time.monotonic() - 999.0
    assert cb.should_allow() is False


def test_success_resets_latch() -> None:
    """A successful probe after latching resets the breaker to CLOSED."""
    cb = CircuitBreaker(
        failure_threshold=1,
        cooldown_s=0.0,
        max_cooldown_s=10.0,
        max_reopen_count=1,
    )
    cb.record_failure()
    _cycle_to_half_open_and_fail(cb)  # 1 reopen → latched
    assert cb.should_allow() is False

    # Manually unlatch for the test — simulate external reset
    cb.record_success()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.should_allow() is True
