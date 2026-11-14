from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.scout_dependencies import ScoutDependenciesSchema


class StubScout:
    """Fixed Scout verdict, so tests do not depend on the random-walk data."""

    def __init__(self, verdict: str, pattern: str | None = None) -> None:
        self._decision = ScoutDecisionSchema(
            verdict="INTERESTING" if verdict == "INTERESTING" else "SKIP",
            reason="stub",
            pattern_detected=pattern,
        )

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        return self._decision
