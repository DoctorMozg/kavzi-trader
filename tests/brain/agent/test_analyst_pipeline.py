"""Tests for AnalystPipeline directional-conflict structured logging."""

import logging
from decimal import Decimal

import pytest

from kavzi_trader.brain.agent.analyst_pipeline import AnalystPipeline
from kavzi_trader.brain.agent.decision_dedup import DecisionDeduplicator
from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema
from kavzi_trader.brain.schemas.dependencies import AnalystDependenciesSchema
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
    DualConfluenceSchema,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime

_ANALYST_PIPELINE_LOGGER = "kavzi_trader.brain.agent.analyst_pipeline"


class _NeverCalledAnalyst:
    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        raise AssertionError("analyst.run should not be called")


class _StubDepsFetcher:
    def __init__(self, deps: AnalystDependenciesSchema) -> None:
        self._deps = deps

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        return self._deps


def _make_dual_confluence(long_score: int, short_score: int) -> DualConfluenceSchema:
    def _conf(
        score: int, ema: bool = False, funding: bool = False
    ) -> AlgorithmConfluenceSchema:
        return AlgorithmConfluenceSchema(
            ema_alignment=ema,
            rsi_favorable=False,
            volume_above_average=False,
            price_at_bollinger=False,
            funding_favorable=funding,
            oi_supports_direction=False,
            oi_funding_divergence=False,
            volume_spike=False,
            score=score,
        )

    return DualConfluenceSchema(
        long=_conf(long_score, ema=long_score > 0),
        short=_conf(short_score, funding=short_score > 0),
        detected_side="LONG",
    )


def _make_analyst_deps(
    candle,
    confluence: DualConfluenceSchema,
    regime: VolatilityRegime = VolatilityRegime.NORMAL,
) -> AnalystDependenciesSchema:
    indicators = TechnicalIndicatorsSchema(
        ema_20=Decimal(100),
        ema_50=Decimal(98),
        ema_200=Decimal(90),
        sma_20=Decimal(99),
        rsi_14=Decimal("49.6"),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=None,
        timestamp=utc_now(),
    )
    return AnalystDependenciesSchema(
        symbol="ADAUSDT",
        current_price=Decimal("0.165"),
        timeframe="15m",
        recent_candles=[candle],
        indicators=indicators,
        algorithm_confluence=confluence,
        volatility_regime=regime,
    )


def _make_pipeline(min_algo_confluence: int = 5) -> AnalystPipeline:
    return AnalystPipeline(
        analyst=_NeverCalledAnalyst(),
        dedup=DecisionDeduplicator(),
        min_algo_confluence=min_algo_confluence,
        concurrency_limit=1,
        confluence_override=None,
        log_llm_exception=lambda symbol, agent, exc, elapsed_ms: None,
    )


@pytest.mark.asyncio
async def test_pre_filter_block_includes_directional_conflict_fields(
    caplog, candle
) -> None:
    """When Scout direction (LONG via detected_side) conflicts with higher SHORT
    confluence score, the pre-filter log should carry structured fields that make
    the conflict visible in log analysis tools without parsing the message string.
    """
    # ADAUSDT scenario from the 2026-06-11 run: long=1, short=2 (order flow SHORT).
    # detected_side="LONG" (EMA alignment), but dominant confluence is SHORT.
    confluence = _make_dual_confluence(long_score=1, short_score=2)
    deps = _make_analyst_deps(candle, confluence)

    pipeline = _make_pipeline(min_algo_confluence=5)
    with caplog.at_level(logging.INFO, logger=_ANALYST_PIPELINE_LOGGER):
        result = await pipeline.run("ADAUSDT", _StubDepsFetcher(deps))

    assert result.stop
    assert result.reason == "below_min_algo_confluence"

    # The pre-filter log record must carry directional-conflict structured fields.
    conflict_records = [
        r for r in caplog.records if "max algorithm confluence" in r.getMessage()
    ]
    assert len(conflict_records) == 1, (
        "Expected exactly one 'max algorithm confluence' log record"
    )
    record = conflict_records[0]

    assert hasattr(record, "long_confluence"), (
        "Log record missing 'long_confluence' extra field"
    )
    assert hasattr(record, "short_confluence"), (
        "Log record missing 'short_confluence' extra field"
    )
    assert hasattr(record, "dominant_confluence_side"), (
        "Log record missing 'dominant_confluence_side' extra field"
    )
    assert record.long_confluence == 1
    assert record.short_confluence == 2
    assert record.dominant_confluence_side == "SHORT"


@pytest.mark.asyncio
async def test_pre_filter_block_dominant_side_long_when_long_leads(
    caplog, candle
) -> None:
    """When long confluence is higher, dominant_confluence_side should be LONG."""
    confluence = _make_dual_confluence(long_score=3, short_score=1)
    deps = _make_analyst_deps(candle, confluence)

    pipeline = _make_pipeline(min_algo_confluence=5)
    with caplog.at_level(logging.INFO, logger=_ANALYST_PIPELINE_LOGGER):
        result = await pipeline.run("ADAUSDT", _StubDepsFetcher(deps))

    assert result.reason == "below_min_algo_confluence"
    conflict_records = [
        r for r in caplog.records if "max algorithm confluence" in r.getMessage()
    ]
    assert len(conflict_records) == 1
    assert conflict_records[0].dominant_confluence_side == "LONG"
