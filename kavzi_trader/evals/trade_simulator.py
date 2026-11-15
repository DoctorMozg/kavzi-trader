import logging
from typing import Literal

import numpy as np
import pandas as pd

from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.joined_case_schema import JoinedCaseSchema
from kavzi_trader.evals.sim_trade_schema import SimTradeSchema
from kavzi_trader.evals.triple_barrier import TripleBarrierLabeler

logger = logging.getLogger(__name__)


class TradeSimulator:
    """Walks the Trader's own entry/SL/TP over the cached candles after the decision."""

    def __init__(self, cache: CandleCache) -> None:
        self._cache = cache
        self._frames: dict[str, pd.DataFrame] = {}

    def simulate(
        self, joined: JoinedCaseSchema, *, forced: bool = False
    ) -> SimTradeSchema | None:
        """None without a valid trade; ``forced`` walks a forced Trader's trade."""
        side = joined.forced_trader_side if forced else joined.trader_side
        trader = joined.result.trader
        if side is None or trader is None:
            return None
        entry, stop, target = trader.entry, trader.stop_loss, trader.take_profit
        if entry is None or stop is None or target is None:
            return None
        case = joined.case
        sl_distance, tp_distance = abs(entry - stop), abs(target - entry)
        if sl_distance <= 0 or tp_distance <= 0:
            msg = f"{case.case_id}: degenerate bracket {entry=} {stop=} {target=}"
            raise ValueError(msg)
        frame = self._frame(case.symbol)
        index = int(frame["close_time_ms"].searchsorted(case.decision_close_time_ms))
        if (
            index >= len(frame)
            or frame["close_time_ms"].iloc[index] != case.decision_close_time_ms
        ):
            msg = (
                f"{case.case_id}: decision candle missing from the {case.symbol} cache"
            )
            raise ValueError(msg)
        sign: Literal[1, -1] = 1 if side == "LONG" else -1
        walk = TripleBarrierLabeler(case.generator.horizon_bars).walk_side(
            sign,
            frame["high"].to_numpy(),
            frame["low"].to_numpy(),
            frame["close"].to_numpy(),
            np.array([index], dtype=np.int64),
            np.array([sl_distance]),
            np.array([tp_distance]),
            entry=np.array([entry]),
        )
        outcome = walk.at(0)
        logger.debug("%s %s -> %s", case.case_id, side, outcome.outcome)
        return SimTradeSchema(
            case_id=case.case_id,
            label=case.label.value,
            regime=case.regime,
            tier=case.tier,
            side=side,
            outcome=outcome.outcome,
            r_multiple=outcome.r_multiple,
        )

    def _frame(self, symbol: str) -> pd.DataFrame:
        if symbol not in self._frames:
            frame = self._cache.load(symbol)
            if frame.empty:
                msg = f"No cached candles for {symbol} at {self._cache.path(symbol)}"
                raise FileNotFoundError(msg)
            self._frames[symbol] = frame.sort_values("close_time_ms").reset_index(
                drop=True
            )
        return self._frames[symbol]
