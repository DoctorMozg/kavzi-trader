"""Tests for AnalystPipeline: directional-conflict logging and circuit breaker."""

import logging
from decimal import Decimal

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from kavzi_trader.brain.agent.analyst_pipeline import AnalystPipeline
from kavzi_trader.brain.agent.decision_dedup import DecisionDeduplicator
from kavzi_trader.brain.schemas.dependencies import AnalystDependenciesSchema
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.algorithm_confluence import (
    AlgorithmConfluenceSchema,
    DualConfluenceSchema,
)
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema, KeyLevelsSchema
from kavzi_trader.domain.indicator_schemas import TechnicalIndicatorsSchema
from kavzi_trader.domain.volatility_regime import VolatilityRegime
from kavzi_trader.indicators.htf import HtfTrendSchema

_ANALYST_PIPELINE_LOGGER = "kavzi_trader.brain.agent.analyst_pipeline"


class _NeverCalledAnalyst:
    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        raise AssertionError("analyst.run should not be called")


class _StubDepsFetcher:
    def __init__(self, deps: AnalystDependenciesSchema) -> None:
        self._deps = deps

    async def get_analyst(self, symbol: str) -> AnalystDependenciesSchema:
        return self._deps


def _make_dual_confluence(
    long_score: int,
    short_score: int,
    available_signals: int = 8,
) -> DualConfluenceSchema:
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
            available_signals=available_signals,
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
    htf_trend: HtfTrendSchema | None = None,
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
        htf_trend=htf_trend,
    )


def _make_pipeline(
    min_algo_confluence: int = 5,
    analyst=None,
) -> AnalystPipeline:
    return AnalystPipeline(
        analyst=analyst or _NeverCalledAnalyst(),
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


# ===========================================================================
# Circuit breaker tests (C1 — report_2026_06_11b)
# ===========================================================================


class _FailingAnalyst:
    """Always raises UnexpectedModelBehavior (simulates parse-failure exhaustion)."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        self.call_count += 1
        raise UnexpectedModelBehavior("Exceeded maximum retries", body=None)


class _SuccessAnalyst:
    """Always returns a valid LONG decision."""

    def __init__(self) -> None:
        self.call_count = 0

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        self.call_count += 1
        return AnalystDecisionSchema(
            setup_valid=True,
            direction="LONG",
            confluence_score=7,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning="Bullish EMA stack, RSI 55, volume confirms.",
        )


def _make_high_confluence_deps(candle) -> AnalystDependenciesSchema:
    """Deps that pass the pre-filter (long_score=5 >= min_algo=3) so LLM is called."""
    confluence = _make_dual_confluence(long_score=5, short_score=2)
    return _make_analyst_deps(candle, confluence)


def _make_circuit_pipeline(
    analyst,
    *,
    threshold: int,
    open_cycles: int,
) -> AnalystPipeline:
    return AnalystPipeline(
        analyst=analyst,
        dedup=DecisionDeduplicator(),
        min_algo_confluence=3,
        concurrency_limit=1,
        confluence_override=None,
        log_llm_exception=lambda symbol, agent, exc, elapsed_ms: None,
        circuit_threshold=threshold,
        circuit_open_cycles=open_cycles,
    )


@pytest.mark.asyncio
async def test_analyst_circuit_single_failure_stays_closed(candle) -> None:
    """One parse failure does not open the circuit — next call tries LLM again."""
    analyst = _FailingAnalyst()
    pipeline = _make_circuit_pipeline(analyst, threshold=2, open_cycles=2)
    deps = _make_high_confluence_deps(candle)

    result = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))

    assert result.reason == "agent_error"
    assert analyst.call_count == 1


@pytest.mark.asyncio
async def test_analyst_circuit_opens_after_threshold_failures(candle) -> None:
    """Two parse failures open the circuit; third call returns circuit_open."""
    analyst = _FailingAnalyst()
    pipeline = _make_circuit_pipeline(analyst, threshold=2, open_cycles=2)
    deps = _make_high_confluence_deps(candle)

    r1 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))
    r2 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))
    r3 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))

    assert r1.reason == "agent_error"
    assert r2.reason == "agent_error"
    assert r3.reason == "circuit_open"
    # LLM should NOT have been called on the third attempt
    assert analyst.call_count == 2


@pytest.mark.asyncio
async def test_analyst_circuit_skip_cycles_count_down(candle) -> None:
    """Skip cycles decrement each call; LLM is tried again after they expire."""
    analyst = _FailingAnalyst()
    pipeline = _make_circuit_pipeline(analyst, threshold=2, open_cycles=3)
    deps = _make_high_confluence_deps(candle)

    # Open the circuit with 2 failures
    await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))  # fail 1
    await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))  # fail 2 → opens (3 skip)

    # 3 skip cycles
    r3 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))
    r4 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))
    r5 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))

    # After skip cycles expire, LLM is tried again
    r6 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))

    assert r3.reason == "circuit_open"
    assert r4.reason == "circuit_open"
    assert r5.reason == "circuit_open"
    assert r6.reason == "agent_error"  # LLM tried again
    assert analyst.call_count == 3  # calls 1, 2, and the first post-skip attempt


@pytest.mark.asyncio
async def test_analyst_circuit_resets_on_success_after_skip(candle) -> None:
    """After skip cycles expire and the LLM succeeds, the circuit does not re-open."""
    call_num = 0

    class _FailTwiceThenSucceed:
        async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
            nonlocal call_num
            call_num += 1
            if call_num <= 2:
                raise UnexpectedModelBehavior("boom", body=None)
            return AnalystDecisionSchema(
                setup_valid=False,
                direction="NEUTRAL",
                confluence_score=4,
                key_levels=KeyLevelsSchema(levels=[]),
                reasoning="Recovered.",
            )

    pipeline = _make_circuit_pipeline(
        _FailTwiceThenSucceed(), threshold=2, open_cycles=1
    )
    deps = _make_high_confluence_deps(candle)

    await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))  # fail 1
    await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))  # fail 2 → opens (1 skip)
    r3 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))  # skip (last)
    r4 = await pipeline.run("BTCUSDT", _StubDepsFetcher(deps))  # tries LLM → success

    assert r3.reason == "circuit_open"
    # After skip expires, LLM succeeds → result is not circuit_open
    assert r4.reason != "circuit_open"


# ===========================================================================
# Gates scale with the signals that are actually available
# ===========================================================================


class _FixedScoreAnalyst:
    """Returns a valid LONG verdict with a preset raw confluence score."""

    def __init__(self, score: int) -> None:
        self._score = score
        self.call_count = 0

    async def run(self, deps: AnalystDependenciesSchema) -> AnalystDecisionSchema:
        self.call_count += 1
        return AnalystDecisionSchema(
            setup_valid=True,
            direction="LONG",
            confluence_score=self._score,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=(
                "Fixed verdict used by the gate scaling tests: EMA stack"
                " aligned, volume steady."
            ),
        )


@pytest.fixture
def run_pipeline(candle):
    async def _run(
        *,
        algo_score: int,
        available_signals: int,
        analyst_score: int = 0,
        htf_trend: HtfTrendSchema | None = None,
    ):
        confluence = _make_dual_confluence(algo_score, 0, available_signals)
        deps = _make_analyst_deps(candle, confluence, htf_trend=htf_trend)
        analyst = _FixedScoreAnalyst(analyst_score)
        pipeline = _make_pipeline(min_algo_confluence=3, analyst=analyst)
        result = await pipeline.run("ADAUSDT", _StubDepsFetcher(deps))
        return result, analyst

    return _run


@pytest.mark.asyncio
async def test_algo_2_reaches_analyst_without_order_flow(run_pipeline) -> None:
    result, analyst = await run_pipeline(
        algo_score=2, available_signals=5, analyst_score=5
    )

    assert analyst.call_count == 1
    assert result.reason == "ok"


@pytest.mark.asyncio
async def test_algo_2_still_skipped_with_order_flow(run_pipeline) -> None:
    result, analyst = await run_pipeline(algo_score=2, available_signals=8)

    assert analyst.call_count == 0
    assert result.reason == "below_min_algo_confluence"


@pytest.mark.asyncio
async def test_raw_5_passes_normal_gate_without_order_flow(run_pipeline) -> None:
    result, _ = await run_pipeline(algo_score=3, available_signals=5, analyst_score=5)

    assert not result.stop
    assert result.gates is not None
    assert result.gates.regime_gate == 5


@pytest.mark.asyncio
async def test_raw_5_fails_normal_gate_with_order_flow(run_pipeline) -> None:
    result, _ = await run_pipeline(algo_score=3, available_signals=8, analyst_score=5)

    assert result.stop
    assert result.reason == "invalid_or_below_gate"
    assert result.gates is not None
    assert result.gates.regime_gate == 6


@pytest.mark.asyncio
@pytest.mark.parametrize(("analyst_score", "expect_stop"), [(5, True), (6, False)])
async def test_counter_trend_bump_applies_after_scaling(
    run_pipeline,
    analyst_score: int,
    expect_stop: bool,
) -> None:
    htf = HtfTrendSchema(direction="SHORT", bars_1h=10)

    result, _ = await run_pipeline(
        algo_score=3,
        available_signals=5,
        analyst_score=analyst_score,
        htf_trend=htf,
    )

    assert result.stop is expect_stop
    assert result.gates is not None
    assert result.gates.regime_gate == 5


@pytest.mark.asyncio
async def test_scaled_gates_are_logged_at_info(caplog, run_pipeline) -> None:
    with caplog.at_level(logging.INFO, logger=_ANALYST_PIPELINE_LOGGER):
        await run_pipeline(algo_score=3, available_signals=5, analyst_score=5)

    records = [r for r in caplog.records if "gates scaled" in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert (records[0].available_signals, records[0].base_gate) == (5, 6)
    assert records[0].effective_gate == 5


@pytest.mark.asyncio
async def test_no_scaling_log_with_all_signals(caplog, run_pipeline) -> None:
    with caplog.at_level(logging.INFO, logger=_ANALYST_PIPELINE_LOGGER):
        await run_pipeline(algo_score=3, available_signals=8, analyst_score=6)

    assert not [r for r in caplog.records if "gates scaled" in r.getMessage()]
