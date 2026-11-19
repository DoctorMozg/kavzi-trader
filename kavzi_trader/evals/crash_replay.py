import logging

import numpy as np
import pandas as pd

from kavzi_trader.evals.crash_replay_result_schema import CrashReplayResultSchema
from kavzi_trader.evals.replay_variant_schema import ReplayVariantSchema
from kavzi_trader.evals.stop_fill_schema import StopFillSchema
from kavzi_trader.evals.symbol_replay_schema import SymbolReplaySchema

logger = logging.getLogger(__name__)


class CrashReplay:
    """Replays a long book minute by minute through one day with a disaster stop.

    Positions are held from the previous close; each stop sits ``stop_pct`` below
    that close, as the live executor places it at the rebalance price. Each
    symbol's minutes need ``open_time_ms``, ``low``, ``close`` and ``mark_low``.
    """

    def __init__(self, stop_pct: float, fee: float) -> None:
        if not 0 < stop_pct < 1:
            msg = f"stop_pct must be in (0, 1), got {stop_pct}"
            raise ValueError(msg)
        self._stop_pct = stop_pct
        self._fee = fee

    def run(
        self,
        book: dict[str, float],
        prev_close: dict[str, float],
        minutes: dict[str, pd.DataFrame],
        variant: ReplayVariantSchema,
    ) -> CrashReplayResultSchema:
        times = next(iter(minutes.values()))["open_time_ms"].to_numpy()
        worst_path = np.zeros(len(times))
        end_return = 0.0
        stops: list[StopFillSchema] = []
        for symbol, weight in book.items():
            if weight == 0:
                continue
            replay = self._symbol(symbol, minutes[symbol], prev_close[symbol], variant)
            worst_path += weight * replay.path
            end_return += weight * replay.end_return
            if replay.stop is not None:
                stops.append(replay.stop)
        worst = int(np.argmin(worst_path))
        logger.info("Replay %s: day %.4f", variant.name, end_return)
        return CrashReplayResultSchema(
            name=variant.name,
            end_return=end_return,
            worst_return=float(worst_path[worst]),
            worst_minute=pd.to_datetime(times[worst], unit="ms").strftime("%H:%M"),
            stops=stops,
        )

    def _symbol(
        self,
        symbol: str,
        bars: pd.DataFrame,
        ref: float,
        variant: ReplayVariantSchema,
    ) -> SymbolReplaySchema:
        stop_level = ref * (1 - self._stop_pct)
        halve_from_ms = variant.halve_from_ms.get(symbol)
        size, last, pnl = 1.0, ref, 0.0
        halving = halve_from_ms is not None
        path = np.zeros(len(bars))
        fired: StopFillSchema | None = None
        for i, row in enumerate(bars.itertuples(index=False)):
            if halving and row.open_time_ms >= halve_from_ms:
                # Halved at the previous close, which `last` holds; the half sold
                # is bought back at the next rebalance, so both legs pay the fee.
                halving = False
                pnl -= 2 * self._fee * (size / 2)
                size /= 2
            level = {"contract": row.low, "mark": row.mark_low}.get(variant.trigger)
            if size > 0 and level is not None and level <= stop_level:
                fill = (
                    stop_level if variant.fill == "stop" else min(row.low, stop_level)
                )
                pnl += size * (fill - last) / ref - self._fee * size
                fired = StopFillSchema(
                    symbol=symbol,
                    minute=pd.to_datetime(row.open_time_ms, unit="ms").strftime(
                        "%H:%M"
                    ),
                    fill_return=fill / ref - 1,
                )
                size, last = 0.0, fill
            path[i] = pnl + size * (row.low - last) / ref
            if size > 0:
                pnl += size * (row.close - last) / ref
                last = row.close
        return SymbolReplaySchema(path=path, end_return=pnl, stop=fired)
