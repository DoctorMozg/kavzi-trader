"""Evaluation dataset commands for the KavziTrader CLI."""

import asyncio
import logging
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import click
import httpx2
import numpy as np
import pandas as pd
from pydantic import ValidationError

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.api.exchange_client import ExchangeClient
from kavzi_trader.brain.config import ANTHROPIC_AGENT_DEFAULTS
from kavzi_trader.cli.commands.archive import archive_command
from kavzi_trader.cli.commands.eval_options import (
    SYMBOLS_FILE_OPTION,
    SYMBOLS_OPTION,
    TREND_BUFFER_BAND,
    TREND_TRADING_SYMBOLS,
    parse_lookbacks,
    resolve_symbols,
)
from kavzi_trader.cli.commands.replay import replay_command
from kavzi_trader.cli.commands.trials import trials_command, trials_path
from kavzi_trader.cli.commands.walk_forward import walk_forward_command
from kavzi_trader.cli.composition import build_agent_source, load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.agent_source import AgentSource
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.candidate_signals import (
    CANDIDATE_SIGNALS,
    LEADER_SYMBOL,
    CandidateSignals,
)
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.case_anonymizer import CaseAnonymizer
from kavzi_trader.evals.case_context_builder import CaseContextBuilder
from kavzi_trader.evals.case_dataset_file import CaseDatasetFile
from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.case_selector import CaseSelector
from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.cost_calculator import CostCalculator
from kavzi_trader.evals.dataset_build_params_schema import DatasetBuildParamsSchema
from kavzi_trader.evals.dataset_builder import (
    DAYS_PER_MONTH,
    MS_PER_DAY,
    DatasetBuilder,
)
from kavzi_trader.evals.distribution_report_schema import DistributionReportSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.eval_pipeline_runner import EvalPipelineRunner
from kavzi_trader.evals.eval_run_orchestrator import EvalRunOrchestrator
from kavzi_trader.evals.funding_downloader import FundingDownloader
from kavzi_trader.evals.funding_xs_backtester import FundingXsBacktester
from kavzi_trader.evals.funding_xs_loader import UNIVERSE, FundingXsLoader
from kavzi_trader.evals.funding_xs_metrics import FundingXsMetrics
from kavzi_trader.evals.funding_xs_params_schema import FundingXsParamsSchema
from kavzi_trader.evals.funding_xs_report_renderer import FundingXsReportRenderer
from kavzi_trader.evals.kline_downloader import KlineDownloader
from kavzi_trader.evals.market_feature_builder import MarketFeatureBuilder
from kavzi_trader.evals.metrics_alignment import MetricsAlignment
from kavzi_trader.evals.metrics_cache import MetricsCache
from kavzi_trader.evals.metrics_downloader import MetricsDownloader
from kavzi_trader.evals.oi_downloader import OiDownloader
from kavzi_trader.evals.positioning_signals import (
    POSITIONING_SIGNALS,
    PositioningSignals,
)
from kavzi_trader.evals.result_store import ResultStore
from kavzi_trader.evals.run_header_schema import RunHeaderSchema
from kavzi_trader.evals.run_loader import RunLoader
from kavzi_trader.evals.run_projection_schema import RunProjectionSchema
from kavzi_trader.evals.run_report_builder import RunReportBuilder
from kavzi_trader.evals.sample_window_schema import SampleWindowSchema
from kavzi_trader.evals.scout_signals import ScoutSignals
from kavzi_trader.evals.series_cache import SeriesCache
from kavzi_trader.evals.signal_bracket_schema import SignalBracketSchema
from kavzi_trader.evals.signal_edge_analyzer import SignalEdgeAnalyzer
from kavzi_trader.evals.signal_report_renderer import SignalReportRenderer
from kavzi_trader.evals.signal_sampler import (
    CANDLE_SIGNALS,
    FUNDING_SIGNAL,
    OI_SIGNALS,
    SIDES,
    SignalSampler,
)
from kavzi_trader.evals.sma_filter_signal import SmaFilterSignal
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.trend_report_renderer import TrendReportRenderer
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.evals.vol_managed_hold_signal import VolManagedHoldSignal
from kavzi_trader.evals.weight_backtest import (
    FIRST_RETURN_DAY,
    LAST_RETURN_DAY,
    WeightBacktest,
)
from kavzi_trader.evals.weight_signal import WeightSignal
from kavzi_trader.order_flow.calculator import OrderFlowCalculator
from kavzi_trader.spine.filters.scout import ScoutFilter
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)

_MS_PER_S = 1000
_S_PER_MIN = 60


def _day_start_ms(day: datetime | None) -> int:
    """Midnight UTC of ``day`` (default: today), so same-day reruns agree."""
    moment = day or datetime.now(UTC)
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    return int(midnight.timestamp() * _MS_PER_S)


def _echo_report(report: DistributionReportSchema) -> None:
    for name, value in report.model_dump().items():
        click.echo(f"{name}: {value}")


@click.group("eval")
def eval_group() -> None:
    """Evaluation suite commands."""


@eval_group.command("build-dataset")
@click.option(
    "--months",
    type=click.FloatRange(min=0, min_open=True),
    default=12.0,
    show_default=True,
)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--cases", type=click.IntRange(min=1), default=200, show_default=True)
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("evals/cases_v1.jsonl"),
    show_default=True,
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.option(
    "--end-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Exclusive UTC end of the data window; default today 00:00 UTC.",
)
@click.pass_context
def build_dataset(
    ctx: click.Context,
    months: float,
    seed: int,
    cases: int,
    out: Path,
    cache_dir: Path,
    end_date: datetime | None,
) -> None:
    """Download futures klines and write the frozen triple-barrier eval cases."""
    app_config: AppConfig = ctx.obj["app_config"]
    params = DatasetBuildParamsSchema(
        symbols=app_config.trading.symbols,
        interval=app_config.trading.interval,
        history_candles=app_config.trading.history_candles,
        max_hold_time_hours=app_config.position_management.max_hold_time_hours,
        months=months,
        cases=cases,
        seed=seed,
        data_end_ms=_day_start_ms(end_date),
        cache_dir=cache_dir,
    )

    async def _run() -> None:
        client = BinanceClient()  # public market data, no credentials
        try:
            builder = DatasetBuilder(
                params, app_config.risk, load_tier_registry(), client
            )
            result = await builder.build()
        finally:
            await client.close()
        CaseDatasetFile(out).write(result.cases)
        _echo_report(result.report)
        if any(result.report.shortfall_by_label.values()):
            logger.warning(
                "Dataset short of quota: %s", result.report.shortfall_by_label
            )

    asyncio.run(_run())


def _git_hash() -> str | None:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError, subprocess.CalledProcessError:
        logger.warning("Could not read the git hash for the run header")
        return None
    return done.stdout.strip()


def _run_header(
    app_config: AppConfig,
    run_id: str,
    dataset: Path,
    *,
    bypass: bool,
    force_trader: bool,
    workers: int,
) -> RunHeaderSchema:
    brain = app_config.brain
    analyst_defaults = ANTHROPIC_AGENT_DEFAULTS["analyst"]
    trader_defaults = ANTHROPIC_AGENT_DEFAULTS["trader"]
    return RunHeaderSchema(
        run_id=run_id,
        dataset=str(dataset),
        provider=brain.analyst.provider.value,
        analyst_model=brain.analyst.model_id or analyst_defaults.model_id,
        analyst_effort=brain.analyst.effort or analyst_defaults.effort,
        trader_model=brain.trader.model_id or trader_defaults.model_id,
        trader_effort=brain.trader.effort or trader_defaults.effort,
        bypass_scout=bypass,
        force_trader=force_trader,
        concurrency=workers,
        git_hash=_git_hash(),
    )


def _check_resume(stored: RunHeaderSchema, current: RunHeaderSchema) -> None:
    fields = (
        "analyst_model",
        "trader_model",
        "bypass_scout",
        "force_trader",
        "dataset",
    )
    diffs = [
        f"{f}: run has {getattr(stored, f)!r}, now {getattr(current, f)!r}"
        for f in fields
        if getattr(stored, f) != getattr(current, f)
    ]
    if diffs:
        raise click.UsageError(
            "Cannot resume with a different setup: " + "; ".join(diffs)
        )


def _select_cases(
    cases: list[EvalCaseSchema], ids: str | None, limit: int | None
) -> list[EvalCaseSchema]:
    if ids:
        wanted = [i.strip() for i in ids.split(",") if i.strip()]
        known = {c.case_id for c in cases}
        unknown = [i for i in wanted if i not in known]
        if unknown:
            raise click.UsageError(f"Unknown case ids: {', '.join(unknown)}")
        cases = [c for c in cases if c.case_id in set(wanted)]
    if limit is not None:
        cases = CaseSelector.balanced_head(cases, limit)
    return cases


def _build_runner(
    app_config: AppConfig,
    agents: AgentSource,
    cache_dir: Path,
    *,
    bypass: bool,
    force_trader: bool,
) -> EvalPipelineRunner:
    policy = RegimePolicy(app_config.risk, app_config.scout.extreme_allowed_patterns)
    detector = VolatilityRegimeDetector(app_config.risk, policy)
    history = app_config.trading.history_candles
    return EvalPipelineRunner(
        app_config,
        agents,
        ScoutFilter(app_config.scout, policy),
        CaseAnonymizer(CandleCache(cache_dir, app_config.trading.interval), history),
        CaseContextBuilder(app_config, load_tier_registry(), detector),
        CostCalculator(),
        bypass_scout=bypass,
        force_trader=force_trader,
    )


def _echo_projection(projection: RunProjectionSchema) -> None:
    p = projection
    click.echo(
        f"Dry run: {p.measured_cases} cases measured, "
        f"{p.llm_cases} reached the Analyst LLM"
    )
    click.echo(
        f"  cost/case:    mean ${p.mean_cost_usd:.4f}  max ${p.max_cost_usd:.4f}"
    )
    click.echo(
        f"  latency/case: mean {p.mean_latency_s:.1f}s  max {p.max_latency_s:.1f}s"
    )
    click.echo(
        f"Remaining {p.remaining_cases} cases, {p.reach_fraction:.0%} of them expected "
        "to reach the Analyst LLM (deterministic pre-pass, same gates, no LLM): "
        f"~${p.projected_cost_usd:.2f}, ~{p.projected_time_s / 60:.1f} min"
    )


def _echo_summary(results: list[CaseResultSchema], path: Path) -> None:
    stops = Counter(r.stopped_at or r.status for r in results)
    cost = sum(
        s.metrics.cost_usd or 0.0 for r in results for s in (r.analyst, r.trader) if s
    )
    click.echo(f"Finished {len(results)} cases, cost ${cost:.2f}")
    click.echo("Stopped at: " + ", ".join(f"{k}={v}" for k, v in sorted(stops.items())))
    click.echo(f"Results: {path}")


async def _llm_reaching_ids(
    runner: EvalPipelineRunner, cases: list[EvalCaseSchema]
) -> set[str]:
    """Ids of the cases Scout and the algo-confluence gate let through; no LLM."""
    started = time.monotonic()
    reaching: set[str] = set()
    for case in cases:
        try:
            if await runner.reaches_analyst_llm(case):
                reaching.add(case.case_id)
        except Exception:
            # The real run fails on this case too and records it as an error.
            logger.exception("Pre-pass failed for case %s", case.case_id)
    elapsed_s = time.monotonic() - started
    click.echo(
        f"Pre-pass: {len(reaching)} of {len(cases)} pending cases reach the "
        f"Analyst LLM ({elapsed_s:.1f}s)"
    )
    return reaching


@eval_group.command("run")
@click.option(
    "--dataset",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    default=Path("evals/cases_v1.jsonl"),
    show_default=True,
)
@click.option("--limit", type=click.IntRange(min=1), default=None)
@click.option("--cases", "case_ids", default=None, help="Comma-separated case ids.")
@click.option(
    "--bypass-scout",
    is_flag=True,
    help="Record the Scout verdict but continue to the Analyst on SKIP.",
)
@click.option(
    "--force-trader",
    is_flag=True,
    help="Run the Trader on cases the Analyst gate stopped (scored separately).",
)
@click.option("--concurrency", type=click.IntRange(min=1), default=4, show_default=True)
@click.option("--resume", "resume_id", default=None, help="Run id to continue.")
@click.option("--yes", is_flag=True, help="Skip the confirmation after the dry run.")
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.pass_context
def run_eval(
    ctx: click.Context,
    dataset: Path,
    limit: int | None,
    case_ids: str | None,
    bypass_scout: bool,
    force_trader: bool,
    concurrency: int,
    resume_id: str | None,
    yes: bool,
    cache_dir: Path,
) -> None:
    """Run eval cases through Scout, Analyst and Trader; paid LLM calls."""
    app_config: AppConfig = ctx.obj["app_config"]
    agents: AgentSource = ctx.obj.get("agent_source") or build_agent_source(app_config)
    cases = _select_cases(CaseDatasetFile(dataset).read(), case_ids, limit)
    run_id = resume_id or datetime.now(UTC).strftime("run_%Y%m%dT%H%M%SZ")
    store = ResultStore(app_config.system.results_dir / "evals", run_id)
    header = _run_header(
        app_config,
        run_id,
        dataset,
        bypass=bypass_scout,
        force_trader=force_trader,
        workers=concurrency,
    )
    if resume_id:
        _check_resume(store.read_header(), header)
    else:
        store.write_header(header)
    done = store.completed_ids()
    pending = [c for c in cases if c.case_id not in done]
    click.echo(f"Run {run_id}: {len(pending)} cases to run, {len(done)} already done")

    runner = _build_runner(
        app_config, agents, cache_dir, bypass=bypass_scout, force_trader=force_trader
    )
    orchestrator = EvalRunOrchestrator(runner, store, concurrency)

    async def _drive() -> list[CaseResultSchema]:
        reaching = await _llm_reaching_ids(runner, pending)
        dry_cases = CaseSelector.dry_run(
            pending, app_config.scout.blocked_regimes, reaching_llm=reaching
        )
        results = await orchestrator.run_batch(dry_cases)
        rest = [c for c in pending if c not in dry_cases]
        reach_fraction = (
            sum(c.case_id in reaching for c in rest) / len(rest) if rest else 0.0
        )
        _echo_projection(
            RunProjectionSchema.from_results(
                results, len(rest), concurrency, reach_fraction
            )
        )
        if not rest:
            return results
        if not yes and not click.confirm("Continue with the remaining cases?"):
            raise click.ClickException(
                f"Stopped after the dry run. Resume with: --resume {run_id}"
            )
        return results + await orchestrator.run_batch(rest)

    results = asyncio.run(_drive())
    _echo_summary(results, store.results_path)


@eval_group.command("report")
@click.option("--run", "run_id", required=True, help="Run id to report on.")
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Report path; default results/evals/<run_id>.report.md.",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.pass_context
def report_eval(
    ctx: click.Context, run_id: str, out: Path | None, cache_dir: Path
) -> None:
    """Score a finished run and write a Markdown report; no LLM calls."""
    app_config: AppConfig = ctx.obj["app_config"]
    results_dir = app_config.system.results_dir / "evals"
    builder = RunReportBuilder(RunLoader(results_dir).load(run_id), cache_dir)
    path = out or results_dir / f"{run_id}.report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(builder.markdown(), encoding="utf-8")
    for line in builder.summary():
        click.echo(line)
    click.echo(f"Report: {path}")


# The live z-score needs FUNDING_HISTORY_LIMIT settlements (8h apart) of lead-in.
_FUNDING_LEAD_MS = 40 * 24 * 3600 * _MS_PER_S
_INTERVALS = click.Choice(list(KLINE_INTERVALS))
# Binance rejects openInterestHist start times older than about 30 days.
_OI_LOOKBACK_MS = 29 * 24 * 3600 * _MS_PER_S
_METRICS_TIMEOUT_S = 60.0


def _with_exchange(
    client: ExchangeClient | None,
    job: Callable[[ExchangeClient], Coroutine[None, None, None]],
) -> None:
    """Run ``job`` on the injected client, or on a public one closed afterwards."""

    async def _public() -> None:
        public = BinanceClient()  # public market data, no credentials
        try:
            await job(public)
        finally:
            await public.close()

    asyncio.run(job(client) if client is not None else _public())


def _load_funding(
    client: ExchangeClient | None, cache_dir: Path, frames: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """Download missing funding settlements covering each candle frame."""
    cache = SeriesCache(cache_dir, "funding")

    async def _job(exchange: ExchangeClient) -> None:
        downloader = FundingDownloader(exchange, cache)
        for symbol, frame in frames.items():
            await downloader.ensure_range(
                symbol,
                int(frame["open_time_ms"].iloc[0]) - _FUNDING_LEAD_MS,
                int(frame["close_time_ms"].iloc[-1]) + 1,
            )

    _with_exchange(client, _job)
    return {symbol: cache.load(symbol) for symbol in frames}


def _load_oi(
    client: ExchangeClient | None,
    cache_dir: Path,
    frames: dict[str, pd.DataFrame],
    period: str,
) -> dict[str, pd.DataFrame]:
    """Download the OI snapshots Binance still serves that overlap each frame."""
    cache = SeriesCache(cache_dir, f"oi_{period}")
    oldest_ms = int(time.time() * _MS_PER_S) - _OI_LOOKBACK_MS

    async def _job(exchange: ExchangeClient) -> None:
        downloader = OiDownloader(exchange, cache, period)
        for symbol, frame in frames.items():
            start = max(int(frame["open_time_ms"].iloc[0]), oldest_ms)
            end = int(frame["close_time_ms"].iloc[-1]) + 1
            if start >= end:
                logger.warning("%s candles end before the OI history starts", symbol)
                continue
            await downloader.ensure_range(symbol, start, end)

    _with_exchange(client, _job)
    return {symbol: cache.load(symbol) for symbol in frames}


def _load_metrics(
    cache_dir: Path, frames: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """Download missing archive days covering each candle frame."""
    cache = MetricsCache(cache_dir)

    async def _job() -> None:
        async with httpx2.AsyncClient(timeout=_METRICS_TIMEOUT_S) as http:
            downloader = MetricsDownloader(http, cache)
            for symbol, frame in frames.items():
                await downloader.ensure_range(
                    symbol,
                    int(frame["open_time_ms"].iloc[0]),
                    int(frame["close_time_ms"].iloc[-1]) + 1,
                )

    asyncio.run(_job())
    return {symbol: cache.load(symbol) for symbol in frames}


def _oi_grids(
    archive: dict[str, pd.DataFrame], order_flow: OrderFlowCalculator
) -> dict[str, pd.DataFrame]:
    """Metrics OI on the period grid the live OrderFlowCalculator indexes by."""
    period_ms = KLINE_INTERVALS[order_flow.oi_period] * _MS_PER_S
    return {s: MetricsAlignment.oi_grid(m, period_ms) for s, m in archive.items()}


def _add_positioning(
    history: int,
    frames: dict[str, pd.DataFrame],
    parts: list[pd.DataFrame],
    archive: dict[str, pd.DataFrame],
) -> list[pd.DataFrame]:
    positioning = PositioningSignals(history)
    return [
        positioning.add(frames[s], p, archive[s])
        for s, p in zip(frames, parts, strict=True)
    ]


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / _MS_PER_S, UTC).date().isoformat()


@eval_group.command("refresh-cache")
@click.option(
    "--interval",
    type=_INTERVALS,
    default=None,
    help="Candle interval; default the trading interval.",
)
@click.option(
    "--months",
    type=click.FloatRange(min=0, min_open=True),
    default=12.0,
    show_default=True,
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.option(
    "--metrics/--no-metrics",
    default=False,
    help="Also fill the 5-minute metrics archive (OI and long/short ratios).",
)
@SYMBOLS_OPTION
@click.pass_context
def refresh_cache(
    ctx: click.Context,
    interval: str | None,
    months: float,
    cache_dir: Path,
    metrics: bool,
    symbols: list[str] | None,
) -> None:
    """Fill cached candles, funding and OI up to today; the dataset is untouched."""
    app_config: AppConfig = ctx.obj["app_config"]
    interval = interval or app_config.trading.interval
    end_ms = _day_start_ms(None)
    start_ms = end_ms - int(months * DAYS_PER_MONTH * MS_PER_DAY)
    cache = CandleCache(cache_dir, interval)
    symbols = symbols or app_config.trading.symbols

    async def _job(exchange: ExchangeClient) -> None:
        downloader = KlineDownloader(exchange, cache, interval)
        for symbol in symbols:
            await downloader.ensure_range(symbol, start_ms, end_ms)

    client = ctx.obj.get("exchange_client")
    _with_exchange(client, _job)
    frames = {s: cache.load(s) for s in symbols}
    frames = {s: f for s, f in frames.items() if not f.empty}
    settlements = _load_funding(client, cache_dir, frames)
    period = OrderFlowCalculator(KLINE_INTERVALS[interval] // _S_PER_MIN).oi_period
    snapshots = _load_oi(client, cache_dir, frames, period)
    archive = _load_metrics(cache_dir, frames) if metrics else {}
    for symbol, frame in frames.items():
        first, last = frame["open_time_ms"].iloc[[0, -1]]
        line = (
            f"{symbol}: {len(frame)} {interval} candles {_day(first)} to "
            f"{_day(last)}, {len(settlements[symbol])} funding, "
            f"{len(snapshots[symbol])} OI {period}"
        )
        if metrics:
            line += f", {len(archive[symbol])} metrics 5m"
        click.echo(line)


def _leader(cache: CandleCache, frames: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """BTC candles for the lead signal, from the cache when BTC is not sampled."""
    if LEADER_SYMBOL in frames:
        return frames[LEADER_SYMBOL]
    leader = cache.load(LEADER_SYMBOL).reset_index(drop=True)
    return None if leader.empty else leader


def _add_combos(
    samples: pd.DataFrame, combos: tuple[str, ...], signals: tuple[str, ...]
) -> None:
    """Add a LONG_/SHORT_ column per combo: every listed signal fires on that side."""
    for combo in combos:
        names = combo.split("+")
        unknown = [n for n in names if n not in signals]
        if len(names) < 2 or unknown:  # noqa: PLR2004 - a combo joins two or more
            msg = f"--combo {combo!r}: need 2+ scored signals, unknown {unknown}"
            raise click.BadParameter(msg)
        for side in SIDES:
            columns = [samples[f"{side}_{n}"].to_numpy(dtype=bool) for n in names]
            samples[f"{side}_{combo}"] = np.logical_and.reduce(columns)


def _parse_brackets(
    _ctx: click.Context, _param: click.Parameter, values: tuple[str, ...]
) -> list[SignalBracketSchema]:
    try:
        return [SignalBracketSchema.parse(v) for v in values]
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc


@eval_group.command("signals")
@click.option(
    "--bracket",
    "brackets",
    multiple=True,
    default=("1.5:3:96",),
    show_default=True,
    callback=_parse_brackets,
    help="SL_ATR:TP_ATR:HORIZON_BARS; repeat to compare brackets.",
)
@click.option(
    "--stride",
    type=click.IntRange(min=1),
    default=17,
    show_default=True,
    # Volume is intraday-seasonal; a divisor of 96 would only sample a few
    # times of day (16 bars always hits the same 6 slots).
    help="Sample every Nth bar; keep it coprime with the bars per day.",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Report path; default results/evals/signals_<UTC time>.md.",
)
@click.option(
    "--funding/--no-funding",
    default=False,
    help="Download funding history and score the live funding signal too.",
)
@click.option(
    "--oi/--no-oi",
    default=False,
    help=(
        "Also score the OI signals (implies --funding). Binance keeps about 30 "
        "days of OI, so only bars in that window are sampled."
    ),
)
@click.option(
    "--metrics/--no-metrics",
    default=False,
    help="Score OI and long/short flags from the 5-minute metrics archive, in "
    "place of openInterestHist (implies --funding; excludes --oi).",
)
@click.option(
    "--interval",
    type=_INTERVALS,
    default=None,
    help="Candle interval to test; default the trading interval. Fill it with "
    "refresh-cache first.",
)
@click.option(
    "--from",
    "start_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Only sample bars closing on or after this UTC day; earlier bars still "
    "warm up the indicators.",
)
@click.option(
    "--to",
    "end_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Only sample bars closing before this UTC day (exclusive).",
)
@click.option(
    "--candidates/--no-candidates",
    default=False,
    help="Also score signals the bot does not use yet: taker flow, 1h trend, BTC lead.",
)
@click.option(
    "--scout-vol-min",
    "scout_vol_mins",
    type=click.FloatRange(min=0),
    multiple=True,
    help="Replay the live Scout with this trend_vol_ratio_min and score its "
    "TREND_CONTINUATION calls; repeat to compare thresholds.",
)
@click.option(
    "--combo",
    "combos",
    multiple=True,
    help="A+B: also score bars where all listed signals fire on the same side; "
    "repeatable.",
)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def signal_edge(
    ctx: click.Context,
    brackets: list[SignalBracketSchema],
    stride: int,
    cache_dir: Path,
    out: Path | None,
    funding: bool,
    oi: bool,
    metrics: bool,
    interval: str | None,
    start_day: datetime | None,
    end_day: datetime | None,
    candidates: bool,
    scout_vol_mins: tuple[float, ...],
    combos: tuple[str, ...],
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Measure each confluence signal's R edge on cached candles; no LLM calls."""
    if oi and metrics:
        raise click.UsageError("--oi and --metrics are alternative OI sources")
    app_config: AppConfig = ctx.obj["app_config"]
    history = app_config.trading.history_candles
    interval = interval or app_config.trading.interval
    cache = CandleCache(cache_dir, interval)
    names = resolve_symbols(symbols, symbols_file, app_config.trading.symbols)
    frames = {s: cache.load_traded(s) for s in names}
    frames = {s: f for s, f in frames.items() if not f.empty}
    if not frames:
        msg = (
            f"No cached {interval} candles in {cache_dir}; run "
            f"`eval refresh-cache --interval {interval}`"
        )
        raise click.ClickException(msg)
    order_flow = OrderFlowCalculator(KLINE_INTERVALS[interval] // _S_PER_MIN)
    try:
        window = SampleWindowSchema(
            start_ms=None if start_day is None else _day_start_ms(start_day),
            end_ms=None if end_day is None else _day_start_ms(end_day),
        )
    except ValidationError as exc:
        raise click.BadParameter("--from must be before --to") from exc
    sampler = SignalSampler(
        MarketFeatureBuilder(app_config.risk), history, stride, order_flow, window
    )
    funding = funding or oi or metrics
    max_horizon = max(b.horizon_bars for b in brackets)
    client = ctx.obj.get("exchange_client")
    settlements = _load_funding(client, cache_dir, frames) if funding else {}
    snapshots = _load_oi(client, cache_dir, frames, order_flow.oi_period) if oi else {}
    archive = _load_metrics(cache_dir, frames) if metrics else {}
    snapshots = _oi_grids(archive, order_flow) if metrics else snapshots
    parts = [
        sampler.sample(s, f, max_horizon, settlements.get(s), snapshots.get(s))
        for s, f in frames.items()
    ]
    if metrics:
        parts = _add_positioning(history, frames, parts, archive)
    if candidates:
        extra = CandidateSignals(history, _leader(cache, frames), htf=interval == "15m")
        parts = [extra.add(s, frames[s], p) for s, p in zip(frames, parts, strict=True)]
    scout = ScoutSignals(
        app_config,
        load_tier_registry(),
        interval,
        [Decimal(str(v)) for v in scout_vol_mins],
    )
    if scout_vol_mins:
        parts = [
            asyncio.run(scout.add(s, frames[s], p))
            for s, p in zip(frames, parts, strict=True)
        ]
    parts = [part for part in parts if not part.empty]
    if not parts:
        raise click.ClickException("No bars to sample; is the OI window covered?")
    samples = pd.concat(parts, ignore_index=True)
    signals: tuple[str, ...] = CANDLE_SIGNALS
    if funding:
        signals = (*signals, FUNDING_SIGNAL)
    if oi or metrics:
        signals = (*signals, *OI_SIGNALS, *(POSITIONING_SIGNALS if metrics else ()))
    if candidates:
        signals = (*signals, *[c for c in CANDIDATE_SIGNALS if f"LONG_{c}" in samples])
    signals = (*signals, *scout.names)
    _add_combos(samples, combos, signals)
    signals = (*signals, *combos)
    analyzer = SignalEdgeAnalyzer(
        stride, signals, float(app_config.paper.commission_rate)
    )
    results = [analyzer.analyze(samples, frames, b) for b in brackets]
    renderer = SignalReportRenderer(stride, history, list(frames), interval, window)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"signals_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(renderer.render(results), encoding="utf-8")
    for line in renderer.summary(results):
        click.echo(line)
    click.echo(f"Report: {path}")


@eval_group.command("funding-xs")
@SYMBOLS_OPTION
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Report path; default results/evals/funding_xs_<time>.md.",
)
@click.option("--hold-days", type=click.IntRange(min=1), default=3, show_default=True)
@click.option("--legs", type=click.IntRange(min=1), default=3, show_default=True)
@click.pass_context
def funding_xs(
    ctx: click.Context,
    symbols: list[str] | None,
    cache_dir: Path,
    out: Path | None,
    hold_days: int,
    legs: int,
) -> None:
    """Backtest the pre-registered cross-sectional funding rank, market neutral."""
    app_config: AppConfig = ctx.obj["app_config"]
    names = symbols or list(UNIVERSE)
    cost = float(app_config.paper.commission_rate)
    params = FundingXsParamsSchema(legs=legs, hold_days=hold_days, cost_rate=cost)
    loader = FundingXsLoader(cache_dir)
    try:
        prices = loader.prices(names)
        settlements = loader.settlements(names)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if len(names) < 2 * legs:
        raise click.BadParameter(f"{legs} legs per side need {2 * legs} symbols")
    net_run = FundingXsBacktester(prices, settlements, params).run()
    gross_params = params.model_copy(update={"cost_rate": 0.0})
    gross_run = FundingXsBacktester(prices, settlements, gross_params).run()
    net = FundingXsMetrics.summarize(net_run)
    gross = FundingXsMetrics.summarize(gross_run)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"funding_xs_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    renderer = FundingXsReportRenderer(params, names)
    path.write_text(renderer.render(net_run, net, gross), encoding="utf-8")
    verdict = "PASS" if FundingXsMetrics.passes(net) else "FAIL"
    click.echo(
        f"Net Sharpe {net.sharpe}, annual return {net.annual_return:+.2%}: {verdict}"
    )
    click.echo(f"Report: {path}")


_BENCHMARK_VARIANTS = ("vol-hold", "sma200")


def _trend_rule(
    variant: str, params: TrendParamsSchema
) -> tuple[WeightSignal, str, str]:
    """Signal, report description and trial label of one ``eval trend`` variant."""
    if variant == "vol-hold":
        return VolManagedHoldSignal(params), "Vol-managed hold", variant
    if variant == "sma200":
        return SmaFilterSignal(200), "Long above the 200-day SMA", variant
    lookbacks = ",".join(map(str, params.lookbacks))
    direction = "long/short" if params.long_short else "long/flat"
    return (
        DonchianTrendSignal(params),
        f"Donchian ensemble {direction}, lookbacks [{lookbacks}]",
        f"{variant} lookbacks={lookbacks}",
    )


@eval_group.command("trend")
@click.option(
    "--variant",
    type=click.Choice(["long-flat", "long-short", "vol-hold", "sma200"]),
    default="long-flat",
    show_default=True,
    help=(
        "Donchian long-flat or long-short; vol-hold is always long with the "
        "same sizing; sma200 is unlevered long above the 200-day average."
    ),
)
@click.option(
    "--lookbacks",
    default="20,40,80",
    show_default=True,
    callback=parse_lookbacks,
    help="Donchian lookbacks in days; the preregistered rule uses all three.",
)
@click.option(
    "--archive-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/archive"),
    show_default=True,
    help="Mirror that `eval archive` fills.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Report path; default results/evals/trend_<UTC time>.md.",
)
@click.option(
    "--from",
    "start_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=FIRST_RETURN_DAY.strftime("%Y-%m-%d"),
    show_default=True,
    help="First scored return day (UTC); earlier days only warm up lookbacks.",
)
@click.option(
    "--to",
    "end_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=(LAST_RETURN_DAY + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
    show_default=True,
    help="End of the scored window (UTC day, exclusive).",
)
@click.option(
    "--prereg",
    default=None,
    help="Preregistration file the report cites; default the one for --variant.",
)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def trend_backtest(
    ctx: click.Context,
    variant: str,
    lookbacks: tuple[int, ...],
    archive_dir: Path,
    out: Path | None,
    start_day: datetime,
    end_day: datetime,
    prereg: str | None,
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Backtest the daily Donchian trend ensemble on archived candles and funding."""
    app_config: AppConfig = ctx.obj["app_config"]
    params = TrendParamsSchema(lookbacks=lookbacks, long_short=variant == "long-short")
    signal, rule, label = _trend_rule(variant, params)
    archive = ArchiveSeries(archive_dir)
    try:
        data = TrendDataLoader(archive).load(
            resolve_symbols(symbols, symbols_file, TREND_TRADING_SYMBOLS)
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    backtest = WeightBacktest(
        signal,
        TurnoverBuffer(TREND_BUFFER_BAND),
        TrendPortfolio(float(app_config.paper.commission_rate)),
        TrendMetrics(CashRate.from_csv()),
    )
    last_day = pd.Timestamp(end_day) - pd.Timedelta(days=1)
    try:
        result = backtest.run(data, pd.Timestamp(start_day), last_day)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    renderer = (
        TrendReportRenderer(rule, prereg, "This preregistration decides on it alone.")
        if prereg
        else TrendReportRenderer(
            rule,
            "2026_11_17_trend_vs_simple_benchmarks.md"
            if variant in _BENCHMARK_VARIANTS
            else "2026_11_16_trend_following.md",
        )
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"trend_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(renderer.render(result), encoding="utf-8")
    click.echo(
        f"net Sharpe {result.net.sharpe}, benchmark {result.benchmark.sharpe}, "
        f"criterion met: {renderer.criterion_met(result)}"
    )
    click.echo(f"Report: {path}")
    trial = TrialSchema(
        family="trend",
        variant=(
            f"{label} "
            f"symbols={','.join(result.symbols)} "
            f"fee={app_config.paper.commission_rate} band={TREND_BUFFER_BAND}"
        ),
        first_day=result.first_day,
        last_day=result.last_day,
        daily_net=result.daily_net,
    )
    registry = TrialRegistry(trials_path(app_config))
    if registry.record(trial):
        count = len(registry.trials("trend"))
        click.echo(f"Trial registered; {count} trend trials so far")


eval_group.add_command(replay_command)
eval_group.add_command(trials_command)
eval_group.add_command(archive_command)
eval_group.add_command(walk_forward_command)
