import hashlib
import logging
import math
import random
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.anonymized_case_schema import AnonymizedCaseSchema
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema

logger = logging.getLogger(__name__)

ANONYMOUS_SYMBOL = "ASSET"
_WEEK_MS = 7 * 24 * 3600 * 1000
# Monday 2000-01-03 00:00 UTC; shifting by whole weeks keeps time of day.
_FICTIONAL_EPOCH_MS = 946_857_600_000
# Every case lands in the same price band, so the level names no asset.
_PRICE_BAND = (20.0, 800.0)
_VOLUME_BAND = (50.0, 5000.0)
_VOLUME_REFERENCE_CANDLES = 50
_PRICE_QUANTUM = Decimal("0.0001")
_VOLUME_QUANTUM = Decimal("0.001")
_MS_PER_S = 1000


class CaseAnonymizer:
    """Cuts the no-lookahead window for a case and strips symbol, dates and scale.

    Scaling happens on raw candles, before any indicator exists, so every
    derived number stays consistent with the scaled inputs.
    """

    def __init__(self, cache: CandleCache, history_candles: int) -> None:
        self._cache = cache
        self._history = history_candles
        self._frames: dict[str, pd.DataFrame] = {}

    def anonymize(self, case: EvalCaseSchema) -> AnonymizedCaseSchema:
        window = self._window(case)
        rng = random.Random(
            int.from_bytes(hashlib.sha256(case.case_id.encode()).digest()[:8])
        )
        price_factor = self._factor(rng, _PRICE_BAND, case.entry_price)
        reference_volume = float(
            window["volume"].tail(_VOLUME_REFERENCE_CANDLES).mean()
        )
        volume_factor = self._factor(rng, _VOLUME_BAND, max(reference_volume, 1e-9))
        shift_ms = self._week_shift_ms(case.decision_open_time_ms)
        candles = [
            self._candle(row, price_factor, volume_factor, shift_ms, case.interval)
            for row in self._rows(window)
        ]
        return AnonymizedCaseSchema(
            case_id=case.case_id,
            symbol=ANONYMOUS_SYMBOL,
            candles=candles,
            price_factor=price_factor,
            volume_factor=volume_factor,
            time_shift_ms=shift_ms,
        )

    def _window(self, case: EvalCaseSchema) -> pd.DataFrame:
        frame = self._frames.get(case.symbol)
        if frame is None:
            frame = self._cache.load(case.symbol)
            self._frames[case.symbol] = frame
        # Closed candles only: nothing after the decision close can enter.
        known = frame[frame["close_time_ms"] <= case.decision_close_time_ms]
        window = known.tail(self._history)
        if window.empty or int(window["close_time_ms"].iloc[-1]) != (
            case.decision_close_time_ms
        ):
            msg = (
                f"Cache for {case.symbol} has no candle closing at "
                f"{case.decision_close_time_ms}; rebuild it with eval build-dataset"
            )
            raise ValueError(msg)
        return window

    @staticmethod
    def _rows(window: pd.DataFrame) -> list[Mapping[str, float]]:
        return [
            {str(key): float(value) for key, value in record.items()}
            for record in window.to_dict("records")
        ]

    @staticmethod
    def _factor(
        rng: random.Random, band: tuple[float, float], reference: float
    ) -> Decimal:
        target = math.exp(rng.uniform(math.log(band[0]), math.log(band[1])))
        return Decimal(repr(round(target / reference, 10)))

    @staticmethod
    def _week_shift_ms(decision_open_ms: int) -> int:
        weeks = round((_FICTIONAL_EPOCH_MS - decision_open_ms) / _WEEK_MS)
        return weeks * _WEEK_MS

    @staticmethod
    def _candle(
        row: Mapping[str, float],
        price_factor: Decimal,
        volume_factor: Decimal,
        shift_ms: int,
        interval: str,
    ) -> CandlestickSchema:
        def price(value: float) -> Decimal:
            return (Decimal(repr(value)) * price_factor).quantize(_PRICE_QUANTUM)

        def volume(value: float) -> Decimal:
            return (Decimal(repr(value)) * volume_factor).quantize(_VOLUME_QUANTUM)

        def moment(ms: int) -> datetime:
            return datetime.fromtimestamp((ms + shift_ms) / _MS_PER_S, tz=UTC)

        quote_factor = price_factor * volume_factor
        return CandlestickSchema(
            open_time=moment(int(row["open_time_ms"])),
            open_price=price(row["open"]),
            high_price=price(row["high"]),
            low_price=price(row["low"]),
            close_price=price(row["close"]),
            volume=volume(row["volume"]),
            close_time=moment(int(row["close_time_ms"])),
            quote_volume=(Decimal(repr(row["quote_volume"])) * quote_factor).quantize(
                _VOLUME_QUANTUM
            ),
            trades_count=int(row["trades_count"]),
            taker_buy_base_volume=volume(row["taker_buy_base_volume"]),
            taker_buy_quote_volume=(
                Decimal(repr(row["taker_buy_quote_volume"])) * quote_factor
            ).quantize(_VOLUME_QUANTUM),
            interval=interval,
            symbol=ANONYMOUS_SYMBOL,
        )
