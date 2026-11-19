import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.recorder import UiEventRecorder

logger = logging.getLogger(__name__)


class UiMarketData(Protocol):
    def get_current_price(self, symbol: str) -> Decimal: ...

    def get_candles(self, symbol: str) -> list[CandlestickSchema]: ...


class UiSnapshotLoop:
    """Publishes account state each tick and any candles closed since the last one."""

    def __init__(
        self,
        recorder: UiEventRecorder,
        state_manager: StateManager,
        market_data: UiMarketData,
        symbols: list[str],
        config: UiConfigSchema,
    ) -> None:
        self._recorder = recorder
        self._state_manager = state_manager
        self._market_data = market_data
        self._symbols = symbols
        self._config = config
        self._last_candle_open: dict[str, datetime] = {}

    async def run(self, running_loops: Callable[[], list[str]]) -> None:
        logger.info(
            "UiSnapshotLoop started, interval=%.1fs symbols=%d",
            self._config.snapshot_interval_s,
            len(self._symbols),
        )
        while True:
            try:
                await self.publish_once(running_loops())
            except Exception:
                # Crashing would count toward the supervisor's restart limit and
                # could halt trading over a dashboard fault.
                logger.exception("UI snapshot tick failed, continuing")
            await asyncio.sleep(self._config.snapshot_interval_s)

    async def publish_once(self, running_loops: list[str]) -> None:
        await self._publish_new_candles()
        account = await self._state_manager.get_account_state()
        if account is None:
            logger.debug("No account state yet, skipping UI account tick")
            return
        positions = await self._state_manager.get_all_positions()
        prices = {
            symbol: price
            for symbol in self._symbols
            if (price := self._market_data.get_current_price(symbol)) > 0
        }
        await self._recorder.record_account(account, positions, prices, running_loops)

    async def _publish_new_candles(self) -> None:
        for symbol in self._symbols:
            candles = self._market_data.get_candles(symbol)
            last_open = self._last_candle_open.get(symbol)
            if last_open is None:
                fresh = candles[-self._config.backfill_candles :]
            else:
                fresh = [c for c in candles if c.open_time > last_open]
            if not fresh:
                continue
            interval = fresh[-1].interval
            if interval is None:
                logger.warning("Cached candles for %s carry no interval", symbol)
                continue
            await self._recorder.record_candles(symbol, interval, fresh)
            self._last_candle_open[symbol] = fresh[-1].open_time
