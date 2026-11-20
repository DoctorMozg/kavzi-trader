import asyncio
import logging
import random
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from kavzi_trader.strategies.trend.trend_day_view_schema import TrendDayViewSchema
from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema
from kavzi_trader.strategies.trend.trend_symbol_view_schema import (
    TrendSymbolViewSchema,
)
from kavzi_trader.strategies.trend.trend_view_schema import TrendViewSchema
from kavzi_trader.strategies.trend.vol_spike_config import VolSpikeConfigSchema
from kavzi_trader.strategies.trend.vol_spike_reading_schema import (
    VolSpikeReadingSchema,
)
from kavzi_trader.ui.event_schemas import (
    UiAccountEventSchema,
    UiCandleSchema,
    UiCandlesEventSchema,
    UiDecisionEventSchema,
    UiOpenPositionSchema,
    UiPositionClosedEventSchema,
    UiTradeEventSchema,
)
from kavzi_trader.ui.publisher import UiPublisher
from kavzi_trader.ui.recorder import UiEventRecorder

logger = logging.getLogger(__name__)

_CANDLE_MS = 15 * 60 * 1000
_BACKFILL_CANDLES = 200
_INITIAL_BALANCE = Decimal(10_000)
_QUANT = Decimal("0.01")
_PIPELINE_STEP_CHANCE = 0.35
_EXIT_CHANCE = 0.4
_SCOUT_PASS_CHANCE = 0.5
_ENTRY_CONFIDENCE = 0.6
_DAY_MS = 24 * 60 * 60 * 1000
_HOUR_MS = 60 * 60 * 1000
_TREND_DAYS = 60
_TREND_LOOKBACK = 20
_HELD_WEIGHT = 0.25
_DISASTER_STOP_PCT = 0.15


def _now_ms() -> int:
    return int(time.time() * 1000)


class UiDemoFeed:
    """Publishes synthetic market and pipeline events to exercise the dashboard."""

    def __init__(
        self,
        publisher: UiPublisher,
        symbols: list[str],
        seconds_per_candle: float = 15.0,
        seed: int | None = None,
    ) -> None:
        if not symbols:
            raise ValueError("Demo feed needs at least one symbol")
        self._publisher = publisher
        self._symbols = symbols
        self._seconds_per_candle = seconds_per_candle
        self._rng = random.Random(seed)
        self._started_ms = _now_ms()
        self._prices = {s: Decimal(self._rng.randint(20, 60_000)) for s in symbols}
        self._candle_open_ms = self._started_ms - self._started_ms % _CANDLE_MS
        self._bar: dict[str, list[Decimal]] = {}
        self._positions: dict[str, UiOpenPositionSchema] = {}
        self._realized = Decimal(0)
        self._recorder = UiEventRecorder(
            publisher,
            initial_balance_usdt=_INITIAL_BALANCE,
            is_paper=True,
            session_started_at_ms=self._started_ms,
        )

    async def run(self) -> None:
        await self._backfill()
        await self._publish_trend()
        logger.info("Demo feed running for %s", ", ".join(self._symbols))
        tick = 0
        ticks_per_candle = max(1, round(self._seconds_per_candle))
        while True:
            tick += 1
            self._step_prices()
            await self._publish_account()
            if tick % ticks_per_candle == 0:
                await self._close_candles()
            if self._rng.random() < _PIPELINE_STEP_CHANCE:
                await self._publish_pipeline_step()
            await asyncio.sleep(1)

    async def _backfill(self) -> None:
        for symbol in self._symbols:
            candles = []
            price = self._prices[symbol]
            for i in range(_BACKFILL_CANDLES, 0, -1):
                open_price = price
                price = self._walk(price)
                candles.append(
                    self._candle(
                        self._candle_open_ms - i * _CANDLE_MS,
                        [open_price, max(open_price, price), min(open_price, price)],
                        price,
                    ),
                )
            self._prices[symbol] = price
            self._bar[symbol] = [price, price, price]
            await self._publisher.publish(
                UiCandlesEventSchema(
                    ts_ms=_now_ms(),
                    symbol=symbol,
                    interval="15m",
                    candles=candles,
                ),
            )

    async def _publish_trend(self) -> None:
        """Trend state with a halved held coin, a steady one and a flat one."""
        today_ms = _now_ms() - _now_ms() % _DAY_MS
        symbols = [self._trend_symbol(s, today_ms) for s in self._symbols]
        held = {s.symbol: _HELD_WEIGHT for s in symbols[:2]}
        weights = {s.symbol: held.get(s.symbol, 0.0) for s in symbols}
        hour_ms = _now_ms() - _now_ms() % _HOUR_MS - _HOUR_MS
        halved = symbols[0].symbol
        first_day_ms = symbols[0].days[-4].day_ms
        entry = Decimal(str(symbols[0].days[-4].close))
        self._open_trend_position(halved, entry, first_day_ms + 5 * _HOUR_MS)
        tomorrow = datetime.fromtimestamp(today_ms / 1000, tz=UTC) + timedelta(days=1)
        threshold = 4.0e-5
        view = TrendViewSchema(
            day=datetime.fromtimestamp(today_ms / 1000, tz=UTC).date(),
            lookback=_TREND_LOOKBACK,
            exit_rule="mid",
            next_rebalance_ms=int(tomorrow.timestamp() * 1000) + 60_000,
            rebalanced=False,
            symbols=symbols,
            target_weights=weights,
            held_weights=weights,
            annual_vol_target=0.4,
            max_leverage=1.0,
            vol_window=30,
            buffer_band=0.05,
            disaster_stop_pct=_DISASTER_STOP_PCT,
            vol_spike=VolSpikeConfigSchema(),
            spikes={
                halved: VolSpikeReadingSchema(
                    hour_ms=hour_ms, rv=2.3 * threshold, threshold=threshold
                ),
                symbols[1].symbol: VolSpikeReadingSchema(
                    hour_ms=hour_ms, rv=0.4 * threshold, threshold=threshold
                ),
            }
            if len(symbols) > 1
            else {},
            halvings={
                halved: TrendHalvingSchema(
                    symbol=halved,
                    hour_ms=hour_ms,
                    rv=2.3 * threshold,
                    threshold=threshold,
                    target_weight=_HELD_WEIGHT / 2,
                ),
            },
        )
        await self._recorder.record_trend_view(view)
        await self._recorder.record_halving(view.halvings[halved])

    def _trend_symbol(self, symbol: str, today_ms: int) -> TrendSymbolViewSchema:
        closes = [float(self._prices[symbol])]
        for _ in range(_TREND_DAYS - 1):
            closes.append(closes[-1] / (1 + self._rng.gauss(0.004, 0.025)))
        closes.reverse()
        days = []
        for i, close in enumerate(closes):
            window = closes[max(0, i - _TREND_LOOKBACK) : i]
            full = len(window) == _TREND_LOOKBACK
            upper = max(window) if full else None
            lower = min(window) if full else None
            days.append(
                TrendDayViewSchema(
                    day_ms=today_ms - (_TREND_DAYS - i) * _DAY_MS,
                    close=close,
                    upper=upper,
                    lower=lower,
                    exit=(upper + lower) / 2 if upper and lower else None,
                    signal=1.0 if symbol in self._symbols[:2] else 0.0,
                ),
            )
        last = days[-1]
        return TrendSymbolViewSchema(
            symbol=symbol,
            signal=last.signal,
            close=last.close,
            entry_level=max(closes[-_TREND_LOOKBACK:]),
            exit_level=(max(closes[-_TREND_LOOKBACK:]) + min(closes[-_TREND_LOOKBACK:]))
            / 2,
            annual_vol=0.55,
            days=days,
        )

    def _open_trend_position(
        self, symbol: str, entry: Decimal, opened_at_ms: int
    ) -> None:
        price = self._prices[symbol]
        self._positions[symbol] = UiOpenPositionSchema(
            id=f"demo-trend-{symbol}",
            symbol=symbol,
            side="LONG",
            quantity=(_INITIAL_BALANCE * Decimal(str(_HELD_WEIGHT)) / price).quantize(
                Decimal("0.0001")
            ),
            entry_price=entry.quantize(_QUANT),
            mark_price=price,
            stop_loss=(entry * Decimal(str(1 - _DISASTER_STOP_PCT))).quantize(_QUANT),
            take_profit=None,
            unrealized_pnl_usdt=Decimal(0),
            leverage=1,
            opened_at_ms=opened_at_ms,
        )

    def _step_prices(self) -> None:
        for symbol in self._symbols:
            price = self._walk(self._prices[symbol], volatility=0.0015)
            self._prices[symbol] = price
            bar = self._bar[symbol]
            bar[1], bar[2] = max(bar[1], price), min(bar[2], price)

    async def _close_candles(self) -> None:
        for symbol in self._symbols:
            price = self._prices[symbol]
            candle = self._candle(self._candle_open_ms, self._bar[symbol], price)
            await self._publisher.publish(
                UiCandlesEventSchema(
                    ts_ms=_now_ms(),
                    symbol=symbol,
                    interval="15m",
                    candles=[candle],
                ),
            )
            self._bar[symbol] = [price, price, price]
        self._candle_open_ms += _CANDLE_MS

    async def _publish_pipeline_step(self) -> None:
        # The first symbol is the trend book's held coin; keep it open for the panel.
        symbol = self._rng.choice(self._symbols[1:] or self._symbols)
        if symbol in self._positions and self._rng.random() < _EXIT_CHANCE:
            await self._close_position(symbol)
            return
        interesting = self._rng.random() < _SCOUT_PASS_CHANCE
        await self._decision(
            symbol,
            "scout",
            "INTERESTING" if interesting else "SKIP",
            "EMA ribbon expansion with rising volume"
            if interesting
            else "Range-bound, ATR below threshold",
        )
        if not interesting or symbol in self._positions:
            return
        side = self._rng.choice(["LONG", "SHORT"])
        confluence = self._rng.randint(4, 10)
        await self._decision(
            symbol,
            "analyst",
            side,
            f"Setup valid, confluence {confluence}/11",
            reasoning="Higher-timeframe trend agrees; RSI reset from extreme; "
            "funding neutral; liquidity cluster above recent high.",
            latency_ms=self._rng.randint(900, 2200),
        )
        confidence = round(self._rng.uniform(0.45, 0.92), 2)
        if confidence < _ENTRY_CONFIDENCE:
            await self._decision(
                symbol,
                "trader",
                "WAIT",
                f"Confidence {confidence:.0%} below entry bar",
                confidence=confidence,
                latency_ms=self._rng.randint(2500, 5000),
            )
            return
        await self._decision(
            symbol,
            "trader",
            side,
            f"Enter {side} at market, confidence {confidence:.0%}",
            reasoning="Momentum confirmed on close; stop below swing low keeps "
            "risk at 1R with 2.2R target at prior supply.",
            confidence=confidence,
            latency_ms=self._rng.randint(2500, 5000),
        )
        await self._open_position(symbol, side, confidence)

    async def _open_position(self, symbol: str, side: str, confidence: float) -> None:
        price = self._prices[symbol]
        direction = Decimal(1) if side == "LONG" else Decimal(-1)
        quantity = (Decimal(1000) / price).quantize(Decimal("0.0001"))
        stop = (price * (1 - direction * Decimal("0.01"))).quantize(_QUANT)
        take = (price * (1 + direction * Decimal("0.022"))).quantize(_QUANT)
        self._positions[symbol] = UiOpenPositionSchema(
            id=f"demo-{symbol}-{_now_ms()}",
            symbol=symbol,
            side="LONG" if side == "LONG" else "SHORT",
            quantity=quantity,
            entry_price=price,
            mark_price=price,
            stop_loss=stop,
            take_profit=take,
            unrealized_pnl_usdt=Decimal(0),
            leverage=5,
            opened_at_ms=_now_ms(),
        )
        await self._publisher.publish(
            UiTradeEventSchema(
                ts_ms=_now_ms(),
                symbol=symbol,
                side="LONG" if side == "LONG" else "SHORT",
                status="FILLED",
                confidence=confidence,
                entry_price=price,
                quantity=quantity,
                stop_loss=stop,
                take_profit=take,
                reasoning="Demo entry",
            ),
        )

    async def _close_position(self, symbol: str) -> None:
        position = self._positions.pop(symbol)
        exit_price = self._prices[symbol]
        pnl = self._pnl(position, exit_price)
        self._realized += pnl
        await self._decision(symbol, "position", "FULL_EXIT", "Time exit after stall")
        await self._publisher.publish(
            UiPositionClosedEventSchema(
                ts_ms=_now_ms(),
                symbol=symbol,
                side=position.side,
                quantity=position.quantity,
                entry_price=position.entry_price,
                exit_price=exit_price,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                pnl_usdt=pnl,
                close_reason="time_exit",
                leverage=position.leverage,
                opened_at_ms=position.opened_at_ms,
            ),
        )

    async def _publish_account(self) -> None:
        positions = [
            p.model_copy(
                update={
                    "mark_price": self._prices[p.symbol],
                    "unrealized_pnl_usdt": self._pnl(p, self._prices[p.symbol]),
                },
            )
            for p in self._positions.values()
        ]
        unrealized = sum((p.unrealized_pnl_usdt for p in positions), Decimal(0))
        await self._publisher.publish(
            UiAccountEventSchema(
                ts_ms=_now_ms(),
                session_started_at_ms=self._started_ms,
                is_paper=True,
                initial_balance_usdt=_INITIAL_BALANCE,
                balance_usdt=_INITIAL_BALANCE + self._realized,
                unrealized_pnl_usdt=unrealized,
                positions=positions,
                prices=dict(self._prices),
                running_loops=["ingest", "order_flow", "reasoning", "execution"],
            ),
        )

    async def _decision(
        self,
        symbol: str,
        stage: str,
        verdict: str,
        summary: str,
        reasoning: str | None = None,
        confidence: float | None = None,
        latency_ms: int | None = None,
    ) -> None:
        await self._publisher.publish(
            UiDecisionEventSchema.model_validate(
                {
                    "ts_ms": _now_ms(),
                    "symbol": symbol,
                    "stage": stage,
                    "verdict": verdict,
                    "summary": summary,
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "latency_ms": latency_ms,
                },
            ),
        )

    def _walk(self, price: Decimal, volatility: float = 0.006) -> Decimal:
        change = Decimal(str(round(self._rng.gauss(0, volatility), 6)))
        return (price * (1 + change)).quantize(_QUANT)

    @staticmethod
    def _candle(
        open_time_ms: int,
        ohl: list[Decimal],
        close: Decimal,
    ) -> UiCandleSchema:
        return UiCandleSchema(
            open_time_ms=open_time_ms,
            open=ohl[0],
            high=max(ohl[1], close),
            low=min(ohl[2], close),
            close=close,
            volume=Decimal(1000),
        )

    @staticmethod
    def _pnl(position: UiOpenPositionSchema, price: Decimal) -> Decimal:
        direction = 1 if position.side == "LONG" else -1
        return (
            (price - position.entry_price) * position.quantity * direction
        ).quantize(
            _QUANT,
        )
