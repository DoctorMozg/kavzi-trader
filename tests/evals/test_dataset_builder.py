from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pytest

from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.config import CONFIG_DIR
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.risk_config import RiskConfigSchema
from kavzi_trader.evals.case_dataset_file import CaseDatasetFile
from kavzi_trader.evals.dataset_build_params_schema import DatasetBuildParamsSchema
from kavzi_trader.evals.dataset_builder import DatasetBuilder
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from tests.evals.frames import BASE_MS, STEP_MS, make_frame

BARS = 4000
HORIZON_BARS = 96
SYMBOLS = ["BTCUSDT", "SOLUSDT"]


class SyntheticExchange:
    """Serves a fixed random-walk series per symbol, honouring paging args."""

    def __init__(self) -> None:
        self.frames = {
            s: make_frame(BARS, seed=i, drift_vol=0.003) for i, s in enumerate(SYMBOLS)
        }
        self.requests = 0

    async def get_klines(
        self, symbol: str, interval: str, start_time: int, end_time: int, limit: int
    ) -> list[CandlestickSchema]:
        self.requests += 1
        f = self.frames[symbol]
        part = f[(f["open_time_ms"] >= start_time) & (f["open_time_ms"] <= end_time)]
        return [self._candle(r) for r in part.head(limit).itertuples()]

    @staticmethod
    def _candle(r: object) -> CandlestickSchema:
        def ts(ms: int) -> datetime:
            return datetime.fromtimestamp(ms / 1000, UTC)

        d = lambda v: Decimal(str(v))  # noqa: E731
        return CandlestickSchema(
            open_time=ts(r.open_time_ms),
            open_price=d(r.open),
            high_price=d(r.high),
            low_price=d(r.low),
            close_price=d(r.close),
            volume=d(r.volume),
            close_time=ts(r.close_time_ms),
            quote_volume=d(r.quote_volume),
            trades_count=r.trades_count,
            taker_buy_base_volume=d(r.taker_buy_base_volume),
            taker_buy_quote_volume=d(r.taker_buy_quote_volume),
        )


def _params(tmp_path: Path, seed: int = 7, cases: int = 30) -> DatasetBuildParamsSchema:
    return DatasetBuildParamsSchema(
        symbols=SYMBOLS,
        interval="15m",
        history_candles=300,
        max_hold_time_hours=24,
        months=BARS * STEP_MS / 86_400_000 / (365.25 / 12) - 0.2,
        cases=cases,
        seed=seed,
        data_end_ms=BASE_MS + BARS * STEP_MS,
        cache_dir=tmp_path / "cache",
    )


async def _build(tmp_path: Path, **kwargs: int):
    builder = DatasetBuilder(
        _params(tmp_path, **kwargs),
        RiskConfigSchema(),
        SymbolTierRegistry.from_yaml(CONFIG_DIR / "tiers.yaml"),
        cast("ExchangeClient", SyntheticExchange()),
    )
    return await builder.build()


class TestDatasetBuilder:
    async def test_same_seed_reproduces_the_dataset(self, tmp_path: Path) -> None:
        first = await _build(tmp_path / "a")
        second = await _build(tmp_path / "b")
        assert first.cases == second.cases
        assert first.cases != (await _build(tmp_path / "c", seed=8)).cases

    async def test_cases_respect_quotas_spacing_and_horizon(
        self, tmp_path: Path
    ) -> None:
        result = await _build(tmp_path)
        assert len(result.cases) == 30
        assert set(result.report.selected_by_label.values()) == {10}
        by_symbol = pd.DataFrame(
            [(c.symbol, c.decision_close_time_ms) for c in result.cases],
            columns=["symbol", "t"],
        )
        horizon_ms = HORIZON_BARS * STEP_MS
        for _, group in by_symbol.groupby("symbol"):
            assert (np.diff(sorted(group["t"])) >= horizon_ms).all()
        last_close = BASE_MS + BARS * STEP_MS - 1
        assert all(
            c.decision_close_time_ms <= last_close - horizon_ms for c in result.cases
        )

    async def test_cases_carry_tier_regime_and_bracket(self, tmp_path: Path) -> None:
        result = await _build(tmp_path)
        case = result.cases[0]
        assert case.tier in {"TIER_1", "TIER_2"}
        assert case.tp_atr_multiple == pytest.approx(2 * case.sl_atr_multiple)
        assert case.generator.horizon_bars == HORIZON_BARS

    async def test_warmup_is_excluded_from_first_case(self, tmp_path: Path) -> None:
        result = await _build(tmp_path)
        first_ok = BASE_MS + 299 * STEP_MS
        assert all(c.decision_open_time_ms >= first_ok for c in result.cases)

    async def test_dataset_file_round_trips(self, tmp_path: Path) -> None:
        result = await _build(tmp_path)
        file = CaseDatasetFile(tmp_path / "out" / "cases.jsonl")
        file.write(result.cases)
        assert file.read() == result.cases
