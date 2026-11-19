import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from kavzi_trader.domain.candlestick import CandlestickSchema

logger = logging.getLogger(__name__)

COLUMNS = (
    "open_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time_ms",
    "quote_volume",
    "trades_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
)
_MS_PER_S = 1000


class CandleCache:
    """Gzipped CSV of raw futures candles, one file per symbol and interval."""

    def __init__(self, cache_dir: Path, interval: str) -> None:
        self._dir = cache_dir
        self._interval = interval

    def path(self, symbol: str) -> Path:
        return self._dir / f"{symbol}_{self._interval}.csv.gz"

    def load(self, symbol: str) -> pd.DataFrame:
        path = self.path(symbol)
        if not path.exists():
            return pd.DataFrame(columns=list(COLUMNS)).astype(self._dtypes())
        return pd.read_csv(path, dtype=self._dtypes())

    def load_traded(self, symbol: str) -> pd.DataFrame:
        """Cached candles without zero-volume bars, which Binance keeps serving,
        flat, after a delisting or during a trading pause."""
        frame = self.load(symbol)
        traded = frame[frame["volume"] > 0].reset_index(drop=True)
        dropped = len(frame) - len(traded)
        if dropped:
            logger.info(
                "%s: dropped %d zero-volume candles",
                symbol,
                dropped,
                extra={"symbol": symbol, "dropped": dropped},
            )
        return traded

    def merge(self, symbol: str, candles: list[CandlestickSchema]) -> None:
        """Add candles to the cache, dropping duplicates by open time."""
        if not candles:
            return
        fresh = pd.DataFrame(
            [self._row(c) for c in candles], columns=list(COLUMNS)
        ).astype(self._dtypes())
        existing = self.load(symbol)
        merged = (
            pd.concat([existing, fresh], ignore_index=True)
            .drop_duplicates("open_time_ms", keep="last")
            .sort_values("open_time_ms")
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self.path(symbol)
        # Write-then-rename so an interrupted run never leaves a torn file.
        tmp = path.with_name(path.name + ".tmp")
        merged.to_csv(tmp, index=False, compression="gzip")
        tmp.replace(path)
        logger.debug("Cache %s now holds %d candles", path.name, len(merged))

    @staticmethod
    def _dtypes() -> dict[str, str]:
        ints = {"open_time_ms", "close_time_ms", "trades_count"}
        return {c: "int64" if c in ints else "float64" for c in COLUMNS}

    @staticmethod
    def _row(c: CandlestickSchema) -> dict[str, float | int]:
        return {
            "open_time_ms": int(c.open_time.timestamp() * _MS_PER_S),
            "open": float(c.open_price),
            "high": float(c.high_price),
            "low": float(c.low_price),
            "close": float(c.close_price),
            "volume": float(c.volume),
            "close_time_ms": int(c.close_time.timestamp() * _MS_PER_S),
            "quote_volume": float(c.quote_volume),
            "trades_count": c.trades_count,
            "taker_buy_base_volume": float(c.taker_buy_base_volume),
            "taker_buy_quote_volume": float(c.taker_buy_quote_volume),
        }


def candles_from_frame(
    frame: pd.DataFrame, symbol: str | None = None
) -> list[CandlestickSchema]:
    """Rows of a CandleCache frame as candles, tagged with ``symbol`` if given."""

    def at(ms: int) -> datetime:
        return datetime.fromtimestamp(ms / 1000, UTC)

    return [
        CandlestickSchema(
            open_time=at(int(r.open_time_ms)),
            open_price=Decimal(str(r.open)),
            high_price=Decimal(str(r.high)),
            low_price=Decimal(str(r.low)),
            close_price=Decimal(str(r.close)),
            volume=Decimal(str(r.volume)),
            close_time=at(int(r.close_time_ms)),
            quote_volume=Decimal(str(r.quote_volume)),
            trades_count=int(r.trades_count),
            taker_buy_base_volume=Decimal(str(r.taker_buy_base_volume)),
            taker_buy_quote_volume=Decimal(str(r.taker_buy_quote_volume)),
            symbol=symbol,
        )
        for r in frame.itertuples()
    ]
