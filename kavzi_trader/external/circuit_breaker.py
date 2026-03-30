import logging
import time
from enum import StrEnum

logger = logging.getLogger(__name__)


class CircuitBreakerState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Generic circuit breaker for external data sources.

    States:
      CLOSED  — normal operation, requests pass through.
      OPEN    — requests are blocked; after cooldown, transitions to HALF_OPEN.
      HALF_OPEN — a single probe request is allowed; success → CLOSED,
                  failure → OPEN with doubled cooldown.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_s: float = 900.0,
        max_cooldown_s: float = 3600.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._base_cooldown_s = cooldown_s
        self._max_cooldown_s = max_cooldown_s

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._current_cooldown_s = cooldown_s
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    def should_allow(self) -> bool:
        """Return True if the request should proceed."""
        if self._state == CircuitBreakerState.CLOSED:
            return True

        if self._state == CircuitBreakerState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._current_cooldown_s:
                self._state = CircuitBreakerState.HALF_OPEN
                logger.info(
                    "Circuit breaker HALF_OPEN after %.0fs cooldown",
                    elapsed,
                )
                return True
            return False

        # HALF_OPEN: allow exactly one probe
        return True

    def record_success(self) -> None:
        """Reset breaker on successful request."""
        if self._state != CircuitBreakerState.CLOSED:
            logger.info(
                "Circuit breaker CLOSED after successful probe "
                "(was %s, failures reset)",
                self._state.value,
            )
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._current_cooldown_s = self._base_cooldown_s

    def record_failure(self) -> None:
        """Record a failure. Opens circuit when threshold is reached."""
        self._failure_count += 1

        if self._state == CircuitBreakerState.HALF_OPEN:
            # Probe failed — re-open with doubled cooldown
            self._current_cooldown_s = min(
                self._current_cooldown_s * 2,
                self._max_cooldown_s,
            )
            self._state = CircuitBreakerState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker re-OPENED after failed probe, "
                "next cooldown=%.0fs",
                self._current_cooldown_s,
            )
            return

        if self._failure_count >= self._failure_threshold:
            self._state = CircuitBreakerState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker OPENED after %d consecutive failures, "
                "cooldown=%.0fs",
                self._failure_count,
                self._current_cooldown_s,
            )
