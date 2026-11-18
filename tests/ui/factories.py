from datetime import date
from decimal import Decimal

from kavzi_trader.ui.event_schemas import (
    UiAccountEventSchema,
    UiCandleSchema,
    UiCandlesEventSchema,
    UiDecisionEventSchema,
    UiEvent,
    UiOpenPositionSchema,
    UiPositionClosedEventSchema,
    UiTradeEventSchema,
    UiTrendDaySchema,
    UiTrendStateEventSchema,
    UiTrendSymbolSchema,
)


def make_account(ts_ms: int = 1_000, balance: str = "1050") -> UiAccountEventSchema:
    return UiAccountEventSchema(
        ts_ms=ts_ms,
        session_started_at_ms=0,
        is_paper=True,
        initial_balance_usdt=Decimal(1000),
        balance_usdt=Decimal(balance),
        unrealized_pnl_usdt=Decimal("12.5"),
        positions=[
            UiOpenPositionSchema(
                id="p1",
                symbol="BTCUSDT",
                side="LONG",
                quantity=Decimal("0.01"),
                entry_price=Decimal(60000),
                mark_price=Decimal(61250),
                stop_loss=Decimal(59000),
                take_profit=Decimal(63000),
                unrealized_pnl_usdt=Decimal("12.5"),
                leverage=5,
                opened_at_ms=500,
            ),
        ],
        prices={"BTCUSDT": Decimal(61250)},
        running_loops=["ingest", "reasoning"],
    )


def make_decision(ts_ms: int = 1_000, symbol: str = "BTCUSDT") -> UiDecisionEventSchema:
    return UiDecisionEventSchema(
        ts_ms=ts_ms,
        symbol=symbol,
        stage="scout",
        verdict="INTERESTING",
        summary="EMA cross with volume",
    )


def make_trade(ts_ms: int = 1_000) -> UiTradeEventSchema:
    return UiTradeEventSchema(
        ts_ms=ts_ms,
        symbol="BTCUSDT",
        side="LONG",
        status="FILLED",
        confidence=0.8,
        entry_price=Decimal(60000),
    )


def make_close(ts_ms: int = 1_000, pnl: str = "25") -> UiPositionClosedEventSchema:
    return UiPositionClosedEventSchema(
        ts_ms=ts_ms,
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.01"),
        entry_price=Decimal(60000),
        exit_price=Decimal(62500),
        stop_loss=Decimal(59000),
        take_profit=Decimal(62500),
        pnl_usdt=Decimal(pnl),
        close_reason="take_profit",
        leverage=5,
        opened_at_ms=500,
    )


def make_candles(
    open_times_ms: list[int],
    symbol: str = "BTCUSDT",
    ts_ms: int = 1_000,
) -> UiCandlesEventSchema:
    return UiCandlesEventSchema(
        ts_ms=ts_ms,
        symbol=symbol,
        interval="15m",
        candles=[
            UiCandleSchema(
                open_time_ms=t,
                open=Decimal(1),
                high=Decimal(2),
                low=Decimal("0.5"),
                close=Decimal("1.5"),
                volume=Decimal(10),
            )
            for t in open_times_ms
        ],
    )


class CollectingUiPublisher:
    def __init__(self) -> None:
        self.events: list[UiEvent] = []

    async def publish(self, event: UiEvent) -> None:
        self.events.append(event)

    def decisions(self) -> list[UiDecisionEventSchema]:
        return [e for e in self.events if isinstance(e, UiDecisionEventSchema)]


def make_trend_state(
    ts_ms: int = 1_000, close: float = 100.0
) -> UiTrendStateEventSchema:
    return UiTrendStateEventSchema(
        ts_ms=ts_ms,
        day=date(2026, 11, 17),
        lookback=20,
        next_rebalance_ms=ts_ms + 86_400_000,
        symbols=[
            UiTrendSymbolSchema(
                symbol="BTCUSDT",
                signal=0.0,
                close=close,
                entry_level=120.0,
                exit_level=95.0,
                annual_vol=0.5,
                target_weight=0.0,
                held_weight=0.0,
                days=[UiTrendDaySchema(day_ms=0, close=close, signal=0.0)],
            ),
        ],
    )
