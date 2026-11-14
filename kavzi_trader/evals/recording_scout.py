import logging

from kavzi_trader.brain.agent.protocols import ScoutRunner
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.scout_dependencies import ScoutDependenciesSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime

logger = logging.getLogger(__name__)


class RecordingScout:
    """Runs the real Scout, remembers its verdict, optionally lets SKIPs through."""

    def __init__(self, inner: ScoutRunner, *, bypass: bool) -> None:
        self._inner = inner
        self._bypass = bypass
        self.verdict: ScoutDecisionSchema | None = None
        self.regime: VolatilityRegime | None = None

    async def run(self, deps: ScoutDependenciesSchema) -> ScoutDecisionSchema:
        real = await self._inner.run(deps)
        self.verdict = real
        self.regime = deps.volatility_regime
        if self._bypass and real.verdict != "INTERESTING":
            logger.debug("Scout %s bypassed (%s)", real.verdict, real.reason)
            return ScoutDecisionSchema(
                verdict="INTERESTING",
                reason=f"bypassed {real.verdict}: {real.reason}"[:300],
                pattern_detected=None,
            )
        return real
