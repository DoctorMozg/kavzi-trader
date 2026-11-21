"""Evaluation dataset commands for the KavziTrader CLI."""

import asyncio
import logging
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import click

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.brain.config import ANTHROPIC_AGENT_DEFAULTS
from kavzi_trader.cli.commands.archive import archive_command
from kavzi_trader.cli.commands.buffer_sweep import buffer_sweep_command
from kavzi_trader.cli.commands.combined_mid_halving import (
    combined_mid_halving_command,
)
from kavzi_trader.cli.commands.crash_replay import crash_replay_command
from kavzi_trader.cli.commands.crowding_xs import crowding_xs_command
from kavzi_trader.cli.commands.eval_options import (
    day_start_ms,
)
from kavzi_trader.cli.commands.funding_xs import funding_xs_command
from kavzi_trader.cli.commands.refresh_cache import refresh_cache_command
from kavzi_trader.cli.commands.replay import replay_command
from kavzi_trader.cli.commands.signals import signals_command
from kavzi_trader.cli.commands.trend import trend_command
from kavzi_trader.cli.commands.trend_ablation import trend_ablation_command
from kavzi_trader.cli.commands.trend_timing import trend_timing_command
from kavzi_trader.cli.commands.trials import trials_command
from kavzi_trader.cli.commands.vol_forecast import (
    dvol_download_command,
    vol_forecast_command,
)
from kavzi_trader.cli.commands.walk_forward import walk_forward_command
from kavzi_trader.cli.composition import build_agent_source, load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.agent_source import AgentSource
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.case_anonymizer import CaseAnonymizer
from kavzi_trader.evals.case_context_builder import CaseContextBuilder
from kavzi_trader.evals.case_dataset_file import CaseDatasetFile
from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.case_selector import CaseSelector
from kavzi_trader.evals.cost_calculator import CostCalculator
from kavzi_trader.evals.dataset_build_params_schema import DatasetBuildParamsSchema
from kavzi_trader.evals.dataset_builder import (
    DatasetBuilder,
)
from kavzi_trader.evals.distribution_report_schema import DistributionReportSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.eval_pipeline_runner import EvalPipelineRunner
from kavzi_trader.evals.eval_run_orchestrator import EvalRunOrchestrator
from kavzi_trader.evals.result_store import ResultStore
from kavzi_trader.evals.run_header_schema import RunHeaderSchema
from kavzi_trader.evals.run_loader import RunLoader
from kavzi_trader.evals.run_projection_schema import RunProjectionSchema
from kavzi_trader.evals.run_report_builder import RunReportBuilder
from kavzi_trader.spine.filters.scout import ScoutFilter
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector

logger = logging.getLogger(__name__)


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
        data_end_ms=day_start_ms(end_date),
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


eval_group.add_command(refresh_cache_command)
eval_group.add_command(signals_command)
eval_group.add_command(funding_xs_command)
eval_group.add_command(trend_command)
eval_group.add_command(replay_command)
eval_group.add_command(trials_command)
eval_group.add_command(archive_command)
eval_group.add_command(walk_forward_command)
eval_group.add_command(trend_ablation_command)
eval_group.add_command(buffer_sweep_command)
eval_group.add_command(vol_forecast_command)
eval_group.add_command(dvol_download_command)
eval_group.add_command(crash_replay_command)
eval_group.add_command(combined_mid_halving_command)
eval_group.add_command(trend_timing_command)
eval_group.add_command(crowding_xs_command)
