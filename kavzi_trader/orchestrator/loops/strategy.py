import asyncio
import logging

from kavzi_trader.commons.clock import Clock
from kavzi_trader.commons.system_clock import SYSTEM_CLOCK
from kavzi_trader.orchestrator.loops.decision_publisher import DecisionPublisher
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.strategies.strategy_plugin import StrategyPlugin
from kavzi_trader.strategies.tick_schema import StrategyTickSchema

logger = logging.getLogger(__name__)


class StrategyLoop:
    """Ticks a strategy plugin, queues its intents and sleeps until its next tick."""

    def __init__(
        self,
        plugin: StrategyPlugin,
        publisher: DecisionPublisher,
        state_manager: StateManager | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._plugin = plugin
        self._publisher = publisher
        self._state_manager = state_manager
        self._clock = clock

    async def run(self) -> None:
        logger.info("StrategyLoop started for plugin %s", self._plugin.name)
        while True:
            next_tick_at_ms = await self.step()
            sleep_s = max(0, next_tick_at_ms - self._clock.now_ms()) / 1000
            await asyncio.sleep(sleep_s)

    async def step(self) -> int:
        """Run one plugin tick and queue its intents; returns the next tick time."""
        ctx = await self._build_tick()
        result = await self._plugin.tick(ctx)
        for intent in result.intents:
            # Only a queued intent counts, so a failed push leaves the
            # plugin's state (e.g. cooldowns) untouched.
            if await self._publisher.publish(intent):
                self._plugin.on_enqueued(intent)
        return result.next_tick_at_ms

    async def _build_tick(self) -> StrategyTickSchema:
        if self._state_manager is None:
            return StrategyTickSchema(now_ms=self._clock.now_ms())
        try:
            positions = await self._state_manager.get_all_positions()
            account = await self._state_manager.get_account_state()
        except Exception:
            logger.exception(
                "Failed to fetch state for strategy tick",
                extra={"loop": "strategy", "plugin": self._plugin.name},
            )
            return StrategyTickSchema(now_ms=self._clock.now_ms())
        return StrategyTickSchema(
            now_ms=self._clock.now_ms(),
            account=account,
            positions=positions,
        )
