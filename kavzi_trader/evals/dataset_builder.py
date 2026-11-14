import logging
from collections import Counter
from decimal import Decimal

import numpy as np
import pandas as pd

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.brain.geometry.calculator import TradeGeometryCalculator
from kavzi_trader.brain.geometry.schemas import (
    GeometryInputsSchema,
    GeometryRejectionSchema,
)
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.domain.trade_structure import TradeStructureSchema
from kavzi_trader.evals.barrier_enums import CaseLabel
from kavzi_trader.evals.bracket_policy import BracketPolicy
from kavzi_trader.evals.build_result_schema import BuildResultSchema
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.case_sampler import CaseSampler
from kavzi_trader.evals.dataset_build_params_schema import DatasetBuildParamsSchema
from kavzi_trader.evals.distribution_report_schema import DistributionReportSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.generator_params_schema import GeneratorParamsSchema
from kavzi_trader.evals.kline_downloader import KlineDownloader
from kavzi_trader.evals.market_feature_builder import (
    REGIME_ORDER,
    MarketFeatureBuilder,
)
from kavzi_trader.evals.sampled_ref_schema import SampledRefSchema
from kavzi_trader.evals.symbol_candidates import (
    SymbolCandidateFinder,
    SymbolCandidatesSchema,
)
from kavzi_trader.evals.triple_barrier import TripleBarrierLabeler
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry

logger = logging.getLogger(__name__)

DATASET_VERSION = "v1"
_MS_PER_S = 1000
_MS_PER_HOUR = 3_600_000
_MS_PER_DAY = 86_400_000
_DAYS_PER_MONTH = 365.25 / 12
_GEOMETRY_TOLERANCE = 1e-6


class _SymbolData:
    """A symbol's cached candles with their labeled candidates."""

    def __init__(self, frame: pd.DataFrame, found: SymbolCandidatesSchema) -> None:
        self.frame = frame
        self.found = found
        self.position = {int(i): p for p, i in enumerate(found.entry_idx)}


class DatasetBuilder:
    def __init__(
        self,
        params: DatasetBuildParamsSchema,
        risk_config: RiskConfigSchema,
        tier_registry: SymbolTierRegistry,
        client: ExchangeClient,
    ) -> None:
        self._params = params
        self._risk = risk_config
        self._tiers = tier_registry
        step_ms = KLINE_INTERVALS[params.interval] * _MS_PER_S
        self._step_ms = step_ms
        self._horizon_bars = params.max_hold_time_hours * _MS_PER_HOUR // step_ms
        self._window_start_ms = params.data_end_ms - int(
            params.months * _DAYS_PER_MONTH * _MS_PER_DAY
        )
        self._cache = CandleCache(params.cache_dir, params.interval)
        self._downloader = KlineDownloader(client, self._cache, params.interval)
        self._brackets = BracketPolicy(risk_config)
        self._finder = SymbolCandidateFinder(
            MarketFeatureBuilder(risk_config),
            self._brackets,
            TripleBarrierLabeler(self._horizon_bars),
            params.history_candles,
            self._horizon_bars,
            step_ms,
        )

    async def build(self) -> BuildResultSchema:
        params = self._params
        fetch_start = self._window_start_ms - params.history_candles * self._step_ms
        data: dict[str, _SymbolData] = {}
        for symbol in params.symbols:
            await self._downloader.ensure_range(symbol, fetch_start, params.data_end_ms)
            frame = self._cache.load(symbol)
            frame = frame[
                (frame["open_time_ms"] >= fetch_start)
                & (frame["close_time_ms"] < params.data_end_ms)
            ].reset_index(drop=True)
            if frame.empty:
                msg = f"no candles for {symbol} in the requested range"
                raise ValueError(msg)
            found = self._finder.find(frame, self._window_start_ms)
            data[symbol] = _SymbolData(frame, found)

        candidates = self._candidate_table(data)
        sampler = CaseSampler(
            params.cases,
            params.seed,
            self._horizon_bars,
            [r.value for r in REGIME_ORDER],
        )
        picked = sampler.sample(candidates)
        cases = sorted(
            (self._case(data, ref) for ref in picked),
            key=lambda c: (c.decision_close_time_ms, c.symbol),
        )
        self._verify_geometry(cases)
        report = self._report(candidates, data, cases, sampler.quotas())
        return BuildResultSchema(cases=cases, report=report)

    def _generator_params(self) -> GeneratorParamsSchema:
        params = self._params
        return GeneratorParamsSchema.model_validate(
            {
                "months": params.months,
                "cases": params.cases,
                "symbols": params.symbols,
                "interval": params.interval,
                "history_candles": params.history_candles,
                "horizon_bars": self._horizon_bars,
                "min_spacing_bars": self._horizon_bars,
                "window_start_ms": self._window_start_ms,
                "data_end_ms": params.data_end_ms,
                "stop_atr_by_regime": self._brackets.nominal_stop_atr(),
                "min_rr_ratio": float(self._risk.min_rr_ratio),
            }
        )

    @staticmethod
    def _candidate_table(data: dict[str, _SymbolData]) -> pd.DataFrame:
        parts = []
        for symbol, item in data.items():
            found = item.found
            parts.append(
                pd.DataFrame(
                    {
                        "symbol": symbol,
                        "bar_index": found.entry_idx,
                        "label": [str(lbl) for lbl in found.barriers.labels],
                        "regime": [
                            REGIME_ORDER[c].value
                            for c in found.features.regime_code[found.entry_idx]
                        ],
                    }
                )
            )
        return pd.concat(parts, ignore_index=True)

    def _case(
        self, data: dict[str, _SymbolData], ref: SampledRefSchema
    ) -> EvalCaseSchema:
        item = data[ref.symbol]
        pos = item.position[ref.bar_index]
        row = item.frame.iloc[ref.bar_index]
        found = item.found
        atr = float(found.features.atr[ref.bar_index])
        close_ms = int(row["close_time_ms"])
        return EvalCaseSchema(
            case_id=f"{ref.symbol}-{close_ms}",
            symbol=ref.symbol,
            decision_open_time_ms=int(row["open_time_ms"]),
            decision_close_time_ms=close_ms,
            interval=self._params.interval,
            regime=ref.regime,
            atr_zscore=float(found.features.atr_zscore[ref.bar_index]),
            tier=self._tiers.get_tier(ref.symbol).value,
            entry_price=float(row["close"]),
            atr_14=atr,
            label=ref.label,
            long=found.barriers.long.at(pos),
            short=found.barriers.short.at(pos),
            sl_atr_multiple=float(found.sl_distance[pos]) / atr,
            tp_atr_multiple=float(found.tp_distance[pos]) / atr,
            dataset_version=DATASET_VERSION,
            seed=self._params.seed,
            generator=self._generator_params(),
        )

    def _verify_geometry(self, cases: list[EvalCaseSchema]) -> None:
        """Fail if the vectorised bracket drifts from TradeGeometryCalculator."""
        calculator = TradeGeometryCalculator(self._risk)
        for case in cases:
            nominal = Decimal(str(self._brackets.nominal_stop_atr()[case.regime]))
            inputs = GeometryInputsSchema.model_validate(
                {
                    "symbol": case.symbol,
                    "current_price": Decimal(str(case.entry_price)),
                    "atr_14": Decimal(str(case.atr_14)),
                }
            )
            structure = TradeStructureSchema.model_validate(
                {
                    "direction": "LONG",
                    "stop_atr_multiplier": nominal,
                    "target_style": "ATR_2X",
                }
            )
            geometry = calculator.compute(structure, inputs)
            if isinstance(geometry, GeometryRejectionSchema):
                msg = (
                    f"{case.case_id}: calculator rejects the bracket: {geometry.detail}"
                )
                raise ValueError(msg)  # noqa: TRY004 - a rejection is bad data
            if not (
                np.isclose(
                    float(geometry.sl_atr_multiple),
                    case.sl_atr_multiple,
                    rtol=_GEOMETRY_TOLERANCE,
                )
                and np.isclose(
                    float(
                        (geometry.take_profit - geometry.entry)
                        / Decimal(str(case.atr_14))
                    ),
                    case.tp_atr_multiple,
                    rtol=_GEOMETRY_TOLERANCE,
                )
            ):
                msg = (
                    f"{case.case_id}: bracket "
                    f"{case.sl_atr_multiple}/{case.tp_atr_multiple} "
                    f"differs from calculator {geometry.sl_atr_multiple}"
                )
                raise ValueError(msg)

    def _report(
        self,
        candidates: pd.DataFrame,
        data: dict[str, _SymbolData],
        cases: list[EvalCaseSchema],
        quotas: dict[CaseLabel, int],
    ) -> DistributionReportSchema:
        def pair(a: str, b: str) -> str:
            return f"{a}/{b}"

        by_label = Counter(c.label.value for c in cases)
        return DistributionReportSchema(
            selected_by_label=dict(by_label),
            selected_by_symbol=dict(Counter(c.symbol for c in cases)),
            selected_by_regime=dict(Counter(c.regime for c in cases)),
            selected_by_label_regime=dict(
                Counter(pair(c.label.value, c.regime) for c in cases)
            ),
            selected_by_label_symbol=dict(
                Counter(pair(c.label.value, c.symbol) for c in cases)
            ),
            eligible_by_label=dict(Counter(candidates["label"])),
            eligible_by_regime=dict(Counter(candidates["regime"])),
            eligible_by_label_regime=dict(
                Counter(
                    pair(lbl, reg)
                    for lbl, reg in zip(
                        candidates["label"], candidates["regime"], strict=True
                    )
                )
            ),
            shortfall_by_label={
                lbl.value: quotas[lbl] - by_label.get(lbl.value, 0) for lbl in CaseLabel
            },
            excluded_warmup_or_gap=sum(
                d.found.excluded_warmup_or_gap for d in data.values()
            ),
            excluded_geometry_rejected=sum(
                d.found.excluded_geometry_rejected for d in data.values()
            ),
        )
