import time
from typing import Protocol

from kavzi_trader.strategies.strategy_intent import StrategyIntent
from kavzi_trader.strategies.tick_result_schema import StrategyTickResultSchema
from kavzi_trader.strategies.tick_schema import StrategyTickSchema


def wall_clock_ms() -> int:
    return int(time.time() * 1000)


class StrategyPlugin(Protocol):
    """A source of trade intents driven by a generic scheduling loop."""

    name: str

    async def tick(self, ctx: StrategyTickSchema) -> StrategyTickResultSchema: ...

    def on_enqueued(self, intent: StrategyIntent) -> None:
        """Called only after the intent reached the execution queue."""
        ...
