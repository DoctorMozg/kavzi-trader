from collections import deque

from kavzi_trader.ui.config import UiConfigSchema
from kavzi_trader.ui.event_schemas import (
    UiAccountEventSchema,
    UiCandleSchema,
    UiCandlesEventSchema,
    UiDecisionEventSchema,
    UiEvent,
    UiPositionClosedEventSchema,
    UiTradeEventSchema,
)
from kavzi_trader.ui.message_schemas import UiSnapshotMessageSchema, UiSnapshotSchema


class UiStateProjection:
    """Folds dashboard events into the bounded state every client starts from."""

    def __init__(self, config: UiConfigSchema) -> None:
        self._max_candles = config.max_candles
        self._seq = 0
        self._account: UiAccountEventSchema | None = None
        self._decisions: deque[UiDecisionEventSchema] = deque(
            maxlen=config.max_decisions,
        )
        self._trades: deque[UiTradeEventSchema] = deque(maxlen=config.max_trades)
        self._closed: deque[UiPositionClosedEventSchema] = deque(
            maxlen=config.max_closed_positions,
        )
        self._candles: dict[str, dict[int, UiCandleSchema]] = {}
        self._candle_interval: str | None = None

    @property
    def seq(self) -> int:
        return self._seq

    def apply(self, event: UiEvent) -> int:
        """Fold one event and return the sequence number assigned to it."""
        match event:
            case UiAccountEventSchema():
                self._account = event
            case UiDecisionEventSchema():
                self._decisions.append(event)
            case UiTradeEventSchema():
                self._trades.append(event)
            case UiPositionClosedEventSchema():
                self._closed.append(event)
            case UiCandlesEventSchema():
                self._merge_candles(event)
        self._seq += 1
        return self._seq

    def snapshot_message(self) -> UiSnapshotMessageSchema:
        snapshot = UiSnapshotSchema(
            account=self._account,
            decisions=list(self._decisions),
            trades=list(self._trades),
            closed_positions=list(self._closed),
            candles={
                symbol: [by_time[t] for t in sorted(by_time)]
                for symbol, by_time in self._candles.items()
            },
            candle_interval=self._candle_interval,
        )
        return UiSnapshotMessageSchema(seq=self._seq, snapshot=snapshot)

    def _merge_candles(self, event: UiCandlesEventSchema) -> None:
        # Keyed by open time so a backfill overlapping live closes stays deduped.
        by_time = self._candles.setdefault(event.symbol, {})
        for candle in event.candles:
            by_time[candle.open_time_ms] = candle
        overflow = len(by_time) - self._max_candles
        if overflow > 0:
            for open_time_ms in sorted(by_time)[:overflow]:
                del by_time[open_time_ms]
        self._candle_interval = event.interval
