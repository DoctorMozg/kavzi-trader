from typing import Annotated

from pydantic import BaseModel, ConfigDict, SkipValidation

from kavzi_trader.commons.sim_clock import SimClock
from kavzi_trader.events.store import RedisEventStore
from kavzi_trader.orchestrator.loops.execution import ExecutionLoop
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.orchestrator.loops.strategy import StrategyLoop
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.paper.sim_market_feed import SimMarketFeed


class ReplayRigSchema(BaseModel):
    """The live loops and spine wired to simulated time, prices and storage."""

    # Wired objects, not parsed data, so validation is skipped.
    clock: Annotated[SimClock, SkipValidation]
    feed: Annotated[SimMarketFeed, SkipValidation]
    exchange: Annotated[PaperExchangeClient, SkipValidation]
    market_cache: Annotated[MarketDataCache, SkipValidation]
    event_store: Annotated[RedisEventStore, SkipValidation]
    strategy_loop: Annotated[StrategyLoop, SkipValidation]
    execution_loop: Annotated[ExecutionLoop, SkipValidation]
    position_loop: Annotated[PositionManagementLoop, SkipValidation]
    decision_stream: str
    strategy: str
    symbols: list[str]

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
