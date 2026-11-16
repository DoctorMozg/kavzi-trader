import logging
import re
from collections import Counter, defaultdict
from decimal import Decimal

import pandas as pd

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.candle_cache import candles_from_frame
from kavzi_trader.evals.series_cache import TIME, VALUE
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.orchestrator.loops.decision_queue import FAILED_DECISION_QUEUE_KEY
from kavzi_trader.replay.replay_data_schema import ReplayDataSchema
from kavzi_trader.replay.replay_llm_usage_schema import ReplayLlmUsageSchema
from kavzi_trader.replay.replay_result_schema import ReplayResultSchema
from kavzi_trader.replay.replay_rig_schema import ReplayRigSchema
from kavzi_trader.replay.training_cutoff import is_contaminated
from kavzi_trader.replay.warmup_kline_source import WarmupKlineSource
from kavzi_trader.strategies.trend.trend_following_plugin import DAY_MS

logger = logging.getLogger(__name__)

# Two midnights make one daily return.
_MIN_SAMPLES = 2


class ReplayRunner:
    """Feeds stored bars and funding through the live loops on simulated time."""

    def __init__(self, rig: ReplayRigSchema, data: ReplayDataSchema) -> None:
        self._rig = rig
        self._data = data
        self._prices: dict[str, Decimal] = {}
        self._bar_ms = KLINE_INTERVALS[data.interval] * 1000

    async def run(self, start_ms: int, end_ms: int) -> ReplayResultSchema:
        """Trades from the UTC midnight ``start_ms`` up to ``end_ms``, exclusive."""
        if start_ms % DAY_MS or end_ms % DAY_MS or end_ms <= start_ms:
            msg = f"need UTC midnights with start < end, got {start_ms}, {end_ms}"
            raise ValueError(msg)
        await self._warm_up(start_ms)
        await self._fetch_order_flow()
        bars = self._bars_by_close(start_ms, end_ms)
        funding = self._funding(start_ms, end_ms)
        rig = self._rig
        rig.clock.advance_to(start_ms)
        samples = {start_ms: await self._equity()}
        next_tick_ms = await self._trade(start_ms, start_ms)
        settle_ms = funding[TIME].to_numpy()
        funding_at = 0
        received = Decimal(0)
        for close_ms in sorted(bars):
            rig.clock.advance_to(close_ms)
            for bar in bars[close_ms]:
                await self._settle(bar)
            await self._fetch_order_flow()
            while funding_at < len(settle_ms) and settle_ms[funding_at] <= close_ms:
                received += await self._pay_funding(funding.iloc[funding_at])
                funding_at += 1
            if close_ms % DAY_MS == 0:
                samples[close_ms] = await self._equity()
            if close_ms < end_ms:
                next_tick_ms = await self._trade(next_tick_ms, close_ms)
        return await self._result(samples, received, start_ms)

    async def _trade(self, next_tick_ms: int, close_ms: int) -> int:
        """Runs the strategy ticks due before the next bar closes."""
        rig = self._rig
        # Live polls fills every few seconds, so a stop filled inside the bar
        # is booked before any strategy tick that follows it.
        await rig.position_loop.step()
        while next_tick_ms < close_ms + self._bar_ms:
            rig.clock.advance_to(max(next_tick_ms, close_ms))
            next_tick_ms = await rig.strategy_loop.step()
            await rig.execution_loop.step()
        return next_tick_ms

    async def _warm_up(self, start_ms: int) -> None:
        """Seeds the indicator cache the way a live start backfills it over REST."""
        history = {}
        for symbol, frame in self._data.candles.items():
            closed = frame[frame["open_time_ms"] + self._bar_ms <= start_ms]
            if closed.empty:
                continue
            history[symbol] = candles_from_frame(closed, symbol)
            price = history[symbol][-1].close_price
            self._prices[symbol] = price
            self._rig.feed.set_price(symbol, price)
        await self._rig.market_cache.initialize(
            WarmupKlineSource(history), self._data.interval
        )

    async def _fetch_order_flow(self) -> None:
        # Live polls every few minutes; once per bar sees every closed bar.
        if self._rig.order_flow is not None:
            await self._rig.order_flow.fetch()

    async def _settle(self, bar: CandlestickSchema) -> None:
        symbol = bar.symbol
        if symbol is None:
            raise ValueError(f"Replay bar at {bar.open_time} has no symbol")
        self._prices[symbol] = bar.close_price
        self._rig.feed.set_price(symbol, bar.close_price)
        await self._rig.market_cache.update_candle(symbol, bar, is_closed=True)
        await self._rig.exchange.on_bar(bar)

    async def _pay_funding(self, row: pd.Series) -> Decimal:
        symbol = str(row["symbol"])
        price = self._prices.get(symbol)
        if price is None:
            return Decimal(0)
        rate = Decimal(str(row[VALUE]))
        return await self._rig.exchange.apply_funding(symbol, rate, price)

    async def _equity(self) -> Decimal:
        account = await self._rig.exchange.get_account_info()
        wallet = Decimal(str(account["totalWalletBalance"]))
        return wallet + Decimal(str(account["totalUnrealizedProfit"]))

    def _bars_by_close(
        self, from_ms: int, end_ms: int
    ) -> dict[int, list[CandlestickSchema]]:
        bars: dict[int, list[CandlestickSchema]] = defaultdict(list)
        for symbol, frame in self._data.candles.items():
            close_ms = frame["open_time_ms"] + self._bar_ms
            window = frame[(close_ms > from_ms) & (close_ms <= end_ms)]
            for bar in candles_from_frame(window, symbol):
                close_ms = int(bar.open_time.timestamp() * 1000) + self._bar_ms
                bars[close_ms].append(bar)
        if not bars:
            msg = f"no archived bars close between {from_ms} and {end_ms}"
            raise ValueError(msg)
        return bars

    def _funding(self, start_ms: int, end_ms: int) -> pd.DataFrame:
        frames = [
            frame.assign(symbol=symbol)
            for symbol, frame in self._data.funding.items()
            if not frame.empty
        ]
        if not frames:
            logger.warning("Replay has no funding history; funding is not charged")
            return pd.DataFrame({TIME: [], VALUE: [], "symbol": []})
        merged = pd.concat(frames, ignore_index=True)
        # Settlement stamps run a few ms late; snap them to the second.
        merged[TIME] = merged[TIME] // 1000 * 1000
        merged = merged[(merged[TIME] >= start_ms) & (merged[TIME] < end_ms)]
        return merged.sort_values(TIME, ignore_index=True)

    async def _result(
        self, samples: dict[int, Decimal], received: Decimal, start_ms: int
    ) -> ReplayResultSchema:
        if len(samples) < _MIN_SAMPLES:
            msg = f"replay needs two UTC midnights of equity, got {len(samples)}"
            raise ValueError(msg)
        equity = pd.Series(
            [float(v) for v in samples.values()],
            index=pd.to_datetime(list(samples), unit="ms") - pd.Timedelta(days=1),
        )
        returns = equity.pct_change().dropna()
        values = list(samples.values())
        events = await self._rig.event_store.read(self._rig.decision_stream)
        orders = sum(e.event_type == "order_created" for e in events)
        tally = Counter(
            _reason_kind(reason)
            for e in events
            if e.event_type == "order_rejected"
            for reason in str(e.data.get("reason", "")).split("; ")
        )
        failed = await self._rig.redis_client.client.llen(FAILED_DECISION_QUEUE_KEY)
        if tally and not orders:
            logger.warning("Replay placed no orders; every intent was rejected")
        logger.info(
            "Replay %s done: %d days, equity %s -> %s",
            self._rig.strategy,
            len(returns),
            values[0],
            values[-1],
        )
        return ReplayResultSchema(
            strategy=self._rig.strategy,
            interval=self._data.interval,
            symbols=self._rig.symbols,
            equity=equity,
            stats=TrendMetrics().stats(returns),
            initial_equity=values[0],
            final_equity=values[-1],
            funding_received=received,
            orders=orders,
            failed_decisions=failed,
            rejections=dict(tally.most_common()),
            llm=self._llm_usage(start_ms),
        )

    def _llm_usage(self, start_ms: int) -> ReplayLlmUsageSchema | None:
        agents = self._rig.agents
        if agents is None:
            return None
        if agents.tape_misses:
            logger.error(
                "Replay met %d LLM requests missing from the tape; "
                "those symbols were treated as errors",
                agents.tape_misses,
            )
        return ReplayLlmUsageSchema(
            models=agents.model_names,
            provider_calls=agents.provider_calls,
            tape_misses=agents.tape_misses,
            contaminated=is_contaminated(agents.model_names, start_ms),
        )


def _reason_kind(reason: str) -> str:
    """A rejection reason without its numbers, so equal causes group together."""
    return re.sub(r"\d[\d.,]*", "N", reason.split(" (", maxsplit=1)[0]).strip()
