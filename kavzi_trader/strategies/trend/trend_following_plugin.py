import asyncio
import logging
from datetime import UTC, date, datetime
from decimal import Decimal

import numpy as np

from kavzi_trader.strategies.strategy_intent import StrategyIntent
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from kavzi_trader.strategies.tick_result_schema import StrategyTickResultSchema
from kavzi_trader.strategies.tick_schema import StrategyTickSchema
from kavzi_trader.strategies.trend.daily_close_provider import DailyCloseProvider
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_following_config import (
    TrendFollowingConfigSchema,
)
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)

DAY_MS = 86_400_000
# Run a minute after the daily close so Binance has published the final bar.
REBALANCE_DELAY_MS = 60_000
RETRY_DELAY_MS = 300_000
INTENT_TTL_MS = 3_600_000
# Donchian state is path dependent; this much history keeps it settled.
HISTORY_DAYS = 250


class TrendFollowingPlugin:
    """Daily long/flat Donchian trend rule, rebalanced once per UTC day."""

    name = "trend_following"

    def __init__(
        self,
        config: TrendFollowingConfigSchema,
        bars: DailyCloseProvider,
        store: TrendStateStore,
    ) -> None:
        self._symbols = config.symbols
        self._disaster_stop_pct = config.disaster_stop_pct
        self._signal = DonchianTrendSignal(
            TrendParamsSchema(
                lookbacks=tuple(config.lookbacks),
                vol_window=config.vol_window,
                annual_vol_target=config.annual_vol_target,
                max_leverage=config.max_leverage,
            )
        )
        self._buffer = TurnoverBuffer(config.buffer_band)
        self._min_bars = max(config.lookbacks) + config.vol_window + 1
        self._bars = bars
        self._store = store
        self._last_day: date | None = None
        self._weights: dict[str, float] = {}
        self._loaded = False
        self._saves: set[asyncio.Task[None]] = set()

    async def tick(self, ctx: StrategyTickSchema) -> StrategyTickResultSchema:
        if not self._loaded:
            state = await self._store.load()
            self._last_day = state.last_rebalance_day
            self._weights = dict(state.weights)
            self._loaded = True
            logger.info(
                "Trend state loaded: last_day=%s weights=%s",
                self._last_day,
                self._weights,
            )
        today = self._utc_day(ctx.now_ms)
        if self._last_day == today:
            return self._result([], self._next_rebalance_ms(ctx.now_ms))
        try:
            intents = await self._rebalance(ctx.now_ms)
        except Exception:
            logger.exception(
                "Trend rebalance failed, retrying",
                extra={"plugin": self.name, "day": today.isoformat()},
            )
            return self._result([], ctx.now_ms + RETRY_DELAY_MS)
        await self._store.save_day(today)
        self._last_day = today
        return self._result(intents, self._next_rebalance_ms(ctx.now_ms))

    def on_enqueued(self, intent: StrategyIntent) -> None:
        if not isinstance(intent, TargetWeightIntentSchema):
            return
        if intent.strategy != self.name:
            return
        weight = float(intent.target_weight)
        self._weights[intent.symbol] = weight
        # on_enqueued is sync; a failed save only costs a stale buffer baseline.
        task = asyncio.create_task(self._save_weight(intent.symbol, weight))
        self._saves.add(task)
        task.add_done_callback(self._saves.discard)

    async def flush(self) -> None:
        """Waits for pending weight saves."""
        await asyncio.gather(*self._saves)

    async def _save_weight(self, symbol: str, weight: float) -> None:
        try:
            await self._store.save_weight(symbol, weight)
        except Exception:
            logger.exception(
                "Failed to persist trend weight for %s",
                symbol,
                extra={"plugin": self.name, "symbol": symbol, "weight": weight},
            )

    async def _rebalance(self, now_ms: int) -> list[StrategyIntent]:
        targets = np.array(
            [await self._target_weight(s, now_ms) for s in self._symbols]
        )
        held = np.array([self._weights.get(s, 0.0) for s in self._symbols])
        buffered = self._buffer.step(targets, held)
        intents: list[StrategyIntent] = []
        for symbol, new, old, raw in zip(
            self._symbols, buffered, held, targets, strict=True
        ):
            if new != old:
                reason = f"weight {old:.4f} -> {new:.4f} (raw target {raw:.4f})"
                intents.append(self._intent(symbol, float(new), reason, now_ms))
        logger.info(
            "Trend rebalance %s: %d of %d symbols changed",
            self._utc_day(now_ms),
            len(intents),
            len(self._symbols),
        )
        return intents

    async def _target_weight(self, symbol: str, now_ms: int) -> float:
        closes = await self._bars.closes(symbol, HISTORY_DAYS, now_ms)
        if len(closes) < self._min_bars:
            msg = f"{symbol}: need {self._min_bars} daily bars, got {len(closes)}"
            raise ValueError(msg)
        return float(self._signal.compute(closes, len(self._symbols)).weight[-1])

    def _intent(
        self, symbol: str, weight: float, reason: str, now_ms: int
    ) -> TargetWeightIntentSchema:
        return TargetWeightIntentSchema(
            strategy=self.name,
            intent_id=f"{self.name}:{self._utc_day(now_ms)}:{symbol}",
            symbol=symbol,
            target_weight=Decimal(repr(weight)),
            disaster_stop_pct=self._disaster_stop_pct,
            created_at_ms=now_ms,
            expires_at_ms=now_ms + INTENT_TTL_MS,
            reason=reason,
        )

    @staticmethod
    def _utc_day(now_ms: int) -> date:
        return datetime.fromtimestamp(now_ms / 1000, tz=UTC).date()

    @staticmethod
    def _next_rebalance_ms(now_ms: int) -> int:
        return (now_ms // DAY_MS + 1) * DAY_MS + REBALANCE_DELAY_MS

    @staticmethod
    def _result(
        intents: list[StrategyIntent], next_tick_at_ms: int
    ) -> StrategyTickResultSchema:
        return StrategyTickResultSchema(
            intents=intents, next_tick_at_ms=next_tick_at_ms
        )
