import logging

logger = logging.getLogger(__name__)


class AgentCircuitBreaker:
    """Per-symbol rolling failure counter with a configurable open threshold.

    Tracks consecutive validation failures for a given symbol. When the
    counter reaches ``threshold`` the circuit is considered open and
    callers are expected to skip the downstream LLM call until a
    successful outcome resets the counter via :meth:`reset`.

    Intentionally not a Pydantic model: this is mutable in-process state,
    not a domain value object. The backing ``_failures`` dict is exposed
    for read access via :meth:`failure_count` and direct callers that
    need dict semantics (e.g. legacy tests asserting on the raw store).
    """

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold
        self._failures: dict[str, int] = {}

    @property
    def threshold(self) -> int:
        """Number of consecutive failures required to open the circuit."""
        return self._threshold

    @property
    def failures(self) -> dict[str, int]:
        """Live reference to the per-symbol failure counts.

        Returned by reference on purpose so callers (notably the router's
        backward-compatible ``_trader_validation_failures`` attribute)
        observe mutations without extra plumbing.
        """
        return self._failures

    def failure_count(self, symbol: str) -> int:
        """Return the current consecutive-failure count for ``symbol``."""
        return self._failures.get(symbol, 0)

    def record_failure(self, symbol: str) -> int:
        """Increment and return the failure count for ``symbol``."""
        count = self._failures.get(symbol, 0) + 1
        self._failures[symbol] = count
        return count

    def is_open(self, symbol: str) -> bool:
        """True when ``symbol`` has reached the configured threshold."""
        return self._failures.get(symbol, 0) >= self._threshold

    def reset(self, symbol: str) -> None:
        """Clear the failure counter for ``symbol``.

        No-op when ``symbol`` has no recorded failures.
        """
        self._failures.pop(symbol, None)
