import asyncio
import logging
from collections.abc import Coroutine
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol

import numpy as np

from kavzi_trader.strategies.strategy_intent import StrategyIntent
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from kavzi_trader.strategies.tick_result_schema import StrategyTickResultSchema
from kavzi_trader.strategies.tick_schema import StrategyTickSchema
from kavzi_trader.strategies.trend.daily_close_provider import DailyCloseProvider
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.trend_following_config import (
    TrendFollowingConfigSchema,
)
from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.trend_state_store import TrendStateStore
from kavzi_trader.strategies.trend.trend_view_builder import DAY_MS, TrendViewBuilder
from kavzi_trader.strategies.trend.trend_view_schema import TrendViewSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer
from kavzi_trader.strategies.trend.vol_spike_monitor import HOUR_MS, VolSpikeMonitor
from kavzi_trader.strategies.trend.vol_spike_reading_schema import (
    VolSpikeReadingSchema,
)

logger = logging.getLogger(__name__)

# Run a minute after the daily close so Binance has published the final bar.
REBALANCE_DELAY_MS = 60_000
RETRY_DELAY_MS = 300_000
INTENT_TTL_MS = 3_600_000
# Donchian state is path dependent; this much history keeps it settled.
HISTORY_DAYS = 250
VIEW_DAYS = 120


class EntryReviewer(Protocol):
    async def review_entry(self, symbol: str, as_of_ms: int) -> None: ...


class TrendReporter(Protocol):
    async def record_trend_view(self, view: TrendViewSchema) -> None: ...

    async def record_halving(self, halving: TrendHalvingSchema) -> None: ...


class TrendFollowingPlugin:
    """Daily long/flat Donchian trend rule, rebalanced once per UTC day."""

    name = "trend_following"

    def __init__(
        self,
        config: TrendFollowingConfigSchema,
        bars: DailyCloseProvider,
        store: TrendStateStore,
        reviewer: EntryReviewer | None = None,
        reporter: TrendReporter | None = None,
        spikes: VolSpikeMonitor | None = None,
    ) -> None:
        self._reviewer = reviewer
        self._spikes = spikes
        self._reporter = reporter
        self._symbols = config.symbols
        self._disaster_stop_pct = config.disaster_stop_pct
        signal_type = (
            MidExitTrendSignal if config.exit_rule == "mid" else DonchianTrendSignal
        )
        self._signal = signal_type(
            TrendParamsSchema(
                lookbacks=tuple(config.lookbacks),
                vol_window=config.vol_window,
                annual_vol_target=config.annual_vol_target,
                max_leverage=config.max_leverage,
            )
        )
        self._buffer = TurnoverBuffer(config.buffer_band)
        self._config = config
        self._min_bars = max(config.lookbacks) + config.vol_window + 1
        self._lookback = min(config.lookbacks)
        self._views = TrendViewBuilder(self._signal, self._lookback, VIEW_DAYS)
        self._reported = False
        self._bars = bars
        self._store = store
        self._last_day: date | None = None
        self._weights: dict[str, float] = {}
        self._halvings: dict[str, TrendHalvingSchema] = {}
        self._pending_halvings: dict[str, TrendHalvingSchema] = {}
        self._readings: dict[str, VolSpikeReadingSchema] = {}
        self._last_view: TrendViewSchema | None = None
        self._loaded = False
        self._saves: set[asyncio.Task[None]] = set()

    async def tick(self, ctx: StrategyTickSchema) -> StrategyTickResultSchema:
        if not self._loaded:
            state = await self._store.load()
            self._last_day = state.last_rebalance_day
            self._weights = dict(state.weights)
            self._halvings = dict(state.halvings)
            self._loaded = True
            logger.info(
                "Trend state loaded: last_day=%s weights=%s halved=%s",
                self._last_day,
                self._weights,
                sorted(self._halvings),
            )
        today = self._utc_day(ctx.now_ms)
        if self._last_day == today:
            if self._reporter is not None and not self._reported:
                await self._report_held(ctx.now_ms)
            intents = [] if self._spikes is None else await self._check_spikes(ctx)
            return self._result(intents, self._next_tick_ms(ctx.now_ms))
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
        return self._result(intents, self._next_tick_ms(ctx.now_ms))

    def on_enqueued(self, intent: StrategyIntent) -> None:
        if not isinstance(intent, TargetWeightIntentSchema):
            return
        if intent.strategy != self.name:
            return
        halving = self._pending_halvings.pop(intent.intent_id, None)
        if halving is not None:
            # A halving leaves the rule's weight alone, so the buffer ignores it.
            self._halvings[intent.symbol] = halving
            self._spawn(self._save_halving(halving))
            return
        weight = float(intent.target_weight)
        is_entry = self._weights.get(intent.symbol, 0.0) == 0.0 and weight > 0.0
        self._weights[intent.symbol] = weight
        # on_enqueued is sync; a failed save only costs a stale buffer baseline.
        self._spawn(self._save_weight(intent.symbol, weight))
        if is_entry and self._reviewer is not None:
            self._spawn(
                self._reviewer.review_entry(intent.symbol, intent.created_at_ms)
            )

    async def flush(self) -> None:
        """Waits for pending weight saves and shadow reviews."""
        await asyncio.gather(*self._saves)

    def _spawn(self, job: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(job)
        self._saves.add(task)
        task.add_done_callback(self._saves.discard)

    async def _save_weight(self, symbol: str, weight: float) -> None:
        try:
            await self._store.save_weight(symbol, weight)
        except Exception:
            logger.exception(
                "Failed to persist trend weight for %s",
                symbol,
                extra={"plugin": self.name, "symbol": symbol, "weight": weight},
            )

    async def _save_halving(self, halving: TrendHalvingSchema) -> None:
        try:
            await self._store.save_halving(halving)
        except Exception:
            logger.exception(
                "Failed to persist halving of %s",
                halving.symbol,
                extra={"plugin": self.name, "symbol": halving.symbol},
            )
        if self._reporter is not None:
            try:
                await self._reporter.record_halving(halving)
            except Exception:
                logger.exception("Halving report failed", extra={"plugin": self.name})
        await self._report_spikes()

    async def _check_spikes(self, ctx: StrategyTickSchema) -> list[StrategyIntent]:
        """Halves each held symbol at its first vol spike of the day."""
        if self._spikes is None:
            return []
        held = {
            p.symbol: p
            for p in ctx.positions
            if p.strategy == self.name and p.quantity > 0
        }
        self._readings = {s: r for s, r in self._readings.items() if s in held}
        intents: list[StrategyIntent] = []
        for symbol in self._symbols:
            if symbol not in held:
                continue
            try:
                day = await self._spikes.day(symbol, ctx.now_ms)
            except Exception:
                logger.exception(
                    "Vol spike check failed for %s",
                    symbol,
                    extra={"plugin": self.name, "symbol": symbol},
                )
                continue
            if day.latest is not None:
                self._readings[symbol] = day.latest
            spike = day.first_spike
            if spike is None or spike.threshold is None or symbol in self._halvings:
                continue
            if ctx.account is None or day.price is None:
                logger.warning("Vol spike on %s but no account or price", symbol)
                continue
            equity = ctx.account.total_balance_usdt + ctx.account.unrealized_pnl
            scale = Decimal(repr(self._spikes.config.scale))
            weight = held[symbol].quantity * Decimal(repr(day.price)) * scale / equity
            halving = TrendHalvingSchema(
                symbol=symbol,
                hour_ms=spike.hour_ms,
                rv=spike.rv,
                threshold=spike.threshold,
                target_weight=float(weight),
            )
            intent = self._halving_intent(halving, weight, ctx.now_ms)
            self._pending_halvings[intent.intent_id] = halving
            intents.append(intent)
        await self._report_spikes()
        return intents

    def _halving_intent(
        self, halving: TrendHalvingSchema, weight: Decimal, now_ms: int
    ) -> TargetWeightIntentSchema:
        hour = datetime.fromtimestamp(halving.hour_ms / 1000, tz=UTC)
        logger.info(
            "Vol spike on %s at %s: rv %.3g > threshold %.3g, halving to %.4f",
            halving.symbol,
            hour.isoformat(),
            halving.rv,
            halving.threshold,
            halving.target_weight,
            extra={"plugin": self.name, "symbol": halving.symbol},
        )
        reason = (
            f"vol spike {hour:%H}:00 UTC: 1h variance {halving.rv:.3g} > "
            f"p{self._quantile_pct()} {halving.threshold:.3g}; "
            f"halve until the next rebalance"
        )
        return TargetWeightIntentSchema(
            strategy=self.name,
            intent_id=f"{self.name}:{self._utc_day(now_ms)}:{halving.symbol}:halve",
            symbol=halving.symbol,
            target_weight=weight,
            disaster_stop_pct=self._disaster_stop_pct,
            created_at_ms=now_ms,
            expires_at_ms=now_ms + INTENT_TTL_MS,
            reason=reason,
        )

    def _quantile_pct(self) -> str:
        quantile = 0.0 if self._spikes is None else self._spikes.config.quantile
        return f"{quantile * 100:g}"

    async def _report_spikes(self) -> None:
        """Re-publishes the last view with fresh spike readings and halvings."""
        if self._last_view is None:
            return
        await self._report(
            self._last_view.model_copy(
                update={
                    "rebalanced": False,
                    "spikes": dict(self._readings),
                    "halvings": dict(self._halvings),
                }
            )
        )

    async def _rebalance(self, now_ms: int) -> list[StrategyIntent]:
        closes = await self._fetch_closes(now_ms)
        targets = np.array([self._target_weight(closes[s]) for s in self._symbols])
        held = np.array([self._weights.get(s, 0.0) for s in self._symbols])
        buffered = self._buffer.step(targets, held)
        intents: list[StrategyIntent] = []
        for symbol, new, old, raw in zip(
            self._symbols, buffered, held, targets, strict=True
        ):
            if new != old or symbol in self._halvings:
                reason = f"weight {old:.4f} -> {new:.4f} (raw target {raw:.4f})"
                if symbol in self._halvings:
                    reason += "; restores the vol-spike halving"
                intents.append(self._intent(symbol, float(new), reason, now_ms))
        if self._halvings:
            await self._store.clear_halvings(list(self._halvings))
            self._halvings.clear()
        self._pending_halvings.clear()
        self._readings.clear()
        logger.info(
            "Trend rebalance %s: %d of %d symbols changed",
            self._utc_day(now_ms),
            len(intents),
            len(self._symbols),
        )
        if self._reporter is not None:
            held_now = dict(zip(self._symbols, map(float, buffered), strict=True))
            await self._report(self._view(closes, held_now, now_ms, rebalanced=True))
        return intents

    async def _fetch_closes(self, now_ms: int) -> dict[str, np.ndarray]:
        closes: dict[str, np.ndarray] = {}
        for symbol in self._symbols:
            series = await self._bars.closes(symbol, HISTORY_DAYS, now_ms)
            if len(series) < self._min_bars:
                msg = f"{symbol}: need {self._min_bars} daily bars, got {len(series)}"
                raise ValueError(msg)
            closes[symbol] = series
        return closes

    def _target_weight(self, closes: np.ndarray) -> float:
        return float(self._signal.compute(closes, len(self._symbols)).weight[-1])

    async def _report_held(self, now_ms: int) -> None:
        """After a same-day restart, reports the held state without trading."""
        try:
            closes = await self._fetch_closes(now_ms)
        except Exception:
            logger.exception("Trend view fetch failed", extra={"plugin": self.name})
            return
        held = {s: self._weights.get(s, 0.0) for s in self._symbols}
        await self._report(self._view(closes, held, now_ms, rebalanced=False))

    def _view(
        self,
        closes: dict[str, np.ndarray],
        held: dict[str, float],
        now_ms: int,
        rebalanced: bool,
    ) -> TrendViewSchema:
        # Providers return closed days only, so the last close is yesterday's bar.
        last_day_ms = (now_ms // DAY_MS - 1) * DAY_MS
        return TrendViewSchema(
            day=self._utc_day(now_ms),
            lookback=self._lookback,
            exit_rule=self._config.exit_rule,
            next_rebalance_ms=self._next_rebalance_ms(now_ms),
            rebalanced=rebalanced,
            symbols=[
                self._views.symbol_view(s, closes[s], last_day_ms)
                for s in self._symbols
            ],
            target_weights={s: self._target_weight(closes[s]) for s in self._symbols},
            held_weights=held,
            annual_vol_target=self._config.annual_vol_target,
            max_leverage=self._config.max_leverage,
            vol_window=self._config.vol_window,
            buffer_band=self._config.buffer_band,
            disaster_stop_pct=float(self._disaster_stop_pct),
            vol_spike=None if self._spikes is None else self._spikes.config,
            spikes=dict(self._readings),
            halvings=dict(self._halvings),
        )

    async def _report(self, view: TrendViewSchema) -> None:
        if self._reporter is None:
            return
        self._reported = True
        self._last_view = view
        try:
            await self._reporter.record_trend_view(view)
        except Exception:
            # The dashboard is optional; a reporting fault must not fail a rebalance.
            logger.exception("Trend view report failed", extra={"plugin": self.name})

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

    def _next_tick_ms(self, now_ms: int) -> int:
        """Hourly while halving is on, a minute after each 1m bar of the hour closes."""
        rebalance_ms = self._next_rebalance_ms(now_ms)
        if self._spikes is None:
            return rebalance_ms
        return min(rebalance_ms, (now_ms // HOUR_MS + 1) * HOUR_MS + REBALANCE_DELAY_MS)

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
