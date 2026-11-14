import logging

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from kavzi_trader.evals.barrier_enums import CaseLabel
from kavzi_trader.evals.sampled_ref_schema import SampledRefSchema

logger = logging.getLogger(__name__)

_Cell = tuple[CaseLabel, str, str]


class CaseSampler:
    """Seeded, balanced draw of cases from the labeled candidates.

    Labels get equal quotas. Each pick goes to the least-filled regime for its
    label, then the least-used symbol in that regime. Picked candles block their
    symbol for ``min_spacing_bars`` either side so outcome windows never overlap.
    Labels are served round-robin so none monopolises scarce time slots.
    """

    def __init__(
        self,
        n_cases: int,
        seed: int,
        min_spacing_bars: int,
        regimes: list[str],
    ) -> None:
        if n_cases < 1 or min_spacing_bars < 1:
            msg = (
                f"n_cases and min_spacing_bars must be >= 1: "
                f"{n_cases}, {min_spacing_bars}"
            )
            raise ValueError(msg)
        self._n_cases = n_cases
        self._seed = seed
        self._spacing = min_spacing_bars
        self._regimes = regimes

    def quotas(self) -> dict[CaseLabel, int]:
        base, extra = divmod(self._n_cases, len(CaseLabel))
        return {
            label: base + (1 if i < extra else 0) for i, label in enumerate(CaseLabel)
        }

    def sample(self, candidates: pd.DataFrame) -> list[SampledRefSchema]:
        """``candidates``: columns symbol, bar_index, label, regime."""
        rng = np.random.default_rng(self._seed)
        pools = self._build_pools(candidates)
        symbols = sorted(candidates["symbol"].unique())
        blocked = {
            s: np.zeros(
                int(candidates.loc[candidates["symbol"] == s, "bar_index"].max()) + 1,
                dtype=bool,
            )
            for s in symbols
        }
        quotas = self.quotas()
        picked: list[SampledRefSchema] = []
        per_label_symbol = {(lbl, s): 0 for lbl in CaseLabel for s in symbols}
        per_cell: dict[_Cell, int] = {}
        per_label_regime = {(lbl, r): 0 for lbl in CaseLabel for r in self._regimes}
        counts = dict.fromkeys(CaseLabel, 0)
        active = [lbl for lbl in CaseLabel if quotas[lbl] > 0]

        while active:
            for label in list(active):
                ref = self._pick(
                    label,
                    symbols,
                    pools,
                    blocked,
                    per_label_regime,
                    per_label_symbol,
                    per_cell,
                    rng,
                )
                if ref is None:
                    logger.warning(
                        "Label %s exhausted at %d of %d cases",
                        label,
                        counts[label],
                        quotas[label],
                    )
                    active.remove(label)
                    continue
                picked.append(ref)
                counts[label] += 1
                per_label_regime[(label, ref.regime)] += 1
                per_label_symbol[(label, ref.symbol)] += 1
                cell = (label, ref.regime, ref.symbol)
                per_cell[cell] = per_cell.get(cell, 0) + 1
                lo = max(0, ref.bar_index - self._spacing + 1)
                blocked[ref.symbol][lo : ref.bar_index + self._spacing] = True
                if counts[label] >= quotas[label]:
                    active.remove(label)
        return picked

    def _build_pools(self, candidates: pd.DataFrame) -> dict[_Cell, NDArray[np.int64]]:
        pools: dict[_Cell, NDArray[np.int64]] = {}
        grouped = candidates.groupby(["label", "regime", "symbol"], sort=True)
        for (label, regime, symbol), group in grouped:
            pools[(CaseLabel(label), str(regime), str(symbol))] = np.sort(
                group["bar_index"].to_numpy(dtype=np.int64)
            )
        return pools

    def _pick(
        self,
        label: CaseLabel,
        symbols: list[str],
        pools: dict[_Cell, NDArray[np.int64]],
        blocked: dict[str, NDArray[np.bool_]],
        per_label_regime: dict[tuple[CaseLabel, str], int],
        per_label_symbol: dict[tuple[CaseLabel, str], int],
        per_cell: dict[_Cell, int],
        rng: np.random.Generator,
    ) -> SampledRefSchema | None:
        regime_order = sorted(
            self._regimes, key=lambda r: (per_label_regime[(label, r)], rng.random())
        )
        for regime in regime_order:
            feasible: dict[str, NDArray[np.int64]] = {}
            for symbol in symbols:
                pool = pools.get((label, regime, symbol))
                if pool is None:
                    continue
                pool = pool[~blocked[symbol][pool]]
                pools[(label, regime, symbol)] = pool
                if len(pool):
                    feasible[symbol] = pool
            if not feasible:
                continue
            symbol = min(
                feasible,
                key=lambda s: (
                    per_cell.get((label, regime, s), 0),
                    per_label_symbol[(label, s)],
                    rng.random(),
                ),
            )
            index = int(rng.choice(feasible[symbol]))
            return SampledRefSchema(
                symbol=symbol, bar_index=index, label=label, regime=regime
            )
        return None
