import logging

logger = logging.getLogger(__name__)


class AgentCircuitBreaker:
    """Per-symbol consecutive-failure counter with an optional cooldown.

    When the counter reaches ``threshold`` the circuit is open and callers
    skip the downstream LLM call until :meth:`reset`. With
    ``cooldown_cycles > 0`` the circuit also arms a cycle countdown on
    opening; callers tick it via :meth:`consume_cooldown_cycle` and the
    failure counter clears itself when the last cooldown cycle elapses.

    Intentionally not a Pydantic model: this is mutable in-process state,
    not a domain value object.
    """

    def __init__(self, threshold: int, cooldown_cycles: int = 0) -> None:
        self._threshold = threshold
        self._cooldown_cycles = cooldown_cycles
        self._failures: dict[str, int] = {}
        self._cooldown_remaining: dict[str, int] = {}

    @property
    def threshold(self) -> int:
        """Number of consecutive failures required to open the circuit."""
        return self._threshold

    @property
    def cooldown_cycles(self) -> int:
        """Cycles to skip after the circuit opens (0 = no cooldown)."""
        return self._cooldown_cycles

    @property
    def failures(self) -> dict[str, int]:
        """Live reference to the per-symbol failure counts.

        Returned by reference on purpose so callers (notably tests) can
        read and clear the raw counts.
        """
        return self._failures

    def failure_count(self, symbol: str) -> int:
        """Return the current consecutive-failure count for ``symbol``."""
        return self._failures.get(symbol, 0)

    def record_failure(self, symbol: str) -> int:
        """Increment and return the failure count for ``symbol``.

        Arms the cooldown countdown when this failure opens the circuit.
        """
        count = self._failures.get(symbol, 0) + 1
        self._failures[symbol] = count
        if self._cooldown_cycles > 0 and count >= self._threshold:
            self._cooldown_remaining[symbol] = self._cooldown_cycles
        return count

    def is_open(self, symbol: str) -> bool:
        """True when ``symbol`` has reached the configured threshold."""
        return self._failures.get(symbol, 0) >= self._threshold

    def consume_cooldown_cycle(self, symbol: str) -> int:
        """Spend one cooldown cycle; return cycles remaining before the tick.

        Returns 0 when no cooldown is active (the caller may proceed). When
        the tick spends the last cycle, the failure counter is reset so the
        next evaluation retries cleanly.
        """
        remaining = self._cooldown_remaining.get(symbol, 0)
        if remaining <= 0:
            return 0
        if remaining == 1:
            self.reset(symbol)
        else:
            self._cooldown_remaining[symbol] = remaining - 1
        return remaining

    def reset(self, symbol: str) -> None:
        """Clear the failure counter and any cooldown for ``symbol``."""
        self._failures.pop(symbol, None)
        self._cooldown_remaining.pop(symbol, None)
