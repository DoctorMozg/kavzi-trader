from collections.abc import Callable


class HealthChecker:
    """Aggregates health checks from multiple components."""

    def __init__(self) -> None:
        self._checks: list[Callable[[], bool]] = []

    def register(self, check: Callable[[], bool]) -> None:
        self._checks.append(check)

    def is_healthy(self) -> bool:
        return all(check() for check in self._checks)
