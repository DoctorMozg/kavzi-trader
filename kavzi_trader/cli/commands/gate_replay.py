import asyncio
import logging
from datetime import date, datetime
from pathlib import Path

import click
import pandas as pd

from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.gate_replay_report import GateReplayReport
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.evals.trend_entry_finder import TrendEntryFinder
from kavzi_trader.evals.trend_entry_schema import TrendEntrySchema
from kavzi_trader.evals.weight_backtest import FIRST_RETURN_DAY
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_entry_gate import TrendEntryGate
from kavzi_trader.strategies.trend.trend_gate_log import TrendGateLog
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)


@click.command("gate-replay")
@click.option("--from", "start", type=click.DateTime(["%Y-%m-%d"]), required=True)
@click.option("--to", "end", type=click.DateTime(["%Y-%m-%d"]), required=True)
@click.option(
    "--archive-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/archive"),
    show_default=True,
)
@click.option(
    "--log",
    "log_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("results/trend_gate/replay.jsonl"),
    show_default=True,
    help="Reviews already here (same prompt) are reused, so a rerun costs nothing.",
)
@click.pass_context
def gate_replay_command(
    ctx: click.Context,
    start: datetime,
    end: datetime,
    archive_dir: Path,
    log_path: Path,
) -> None:
    """Run the shadow news gate on past trend entries and score it (paid LLM calls)."""
    app_config: AppConfig = ctx.obj["app_config"]
    entries = _entries(app_config, archive_dir, start.date(), end.date())
    click.echo(
        f"{len(entries)} trend entries between {start:%Y-%m-%d} and {end:%Y-%m-%d}"
    )
    gate = _gate(app_config)
    log = TrendGateLog(log_path)
    done = {(r.symbol, r.as_of) for r in log.read() if r.prompt_sha == gate.prompt_sha}
    todo = [e for e in entries if (e.symbol, e.as_of) not in done]
    click.echo(f"Reviewing {len(todo)} ({len(entries) - len(todo)} already logged)")

    async def _review_all() -> None:
        for entry in todo:
            log.append(await gate.review(entry.symbol, entry.as_of))

    asyncio.run(_review_all())
    reviews = [r for r in log.read() if r.prompt_sha == gate.prompt_sha]
    report = GateReplayReport(entries, reviews)
    out = log_path.with_suffix(".md")
    out.write_text(report.render(), encoding="utf-8")
    click.echo(f"Vetoes {report.vetoes}, veto value {report.veto_value * 100:+.2f}%")
    click.echo(report.decision())
    click.echo(f"Report: {out}")


def _entries(
    app_config: AppConfig, archive_dir: Path, first: date, last: date
) -> list[TrendEntrySchema]:
    trend = app_config.strategy.trend_following
    params = TrendParamsSchema(
        lookbacks=tuple(trend.lookbacks),
        vol_window=trend.vol_window,
        annual_vol_target=trend.annual_vol_target,
        max_leverage=trend.max_leverage,
    )
    try:
        data = TrendDataLoader(ArchiveSeries(archive_dir)).load(trend.symbols)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    finder = TrendEntryFinder(
        DonchianTrendSignal(params),
        TurnoverBuffer(trend.buffer_band),
        float(app_config.paper.commission_rate),
    )
    # Same warm-up start as the trend backtests, so held positions aren't entries.
    warmup = (FIRST_RETURN_DAY - pd.Timedelta(days=1)).date()
    return finder.entries(data, warmup, first, last)


def _gate(app_config: AppConfig) -> TrendEntryGate:
    provider = app_config.brain.gate.provider
    if not app_config.brain.api_key_for(provider).get_secret_value():
        msg = f"No API key for the gate's provider {provider.value}"
        raise click.UsageError(msg)
    prompts = PromptLoader()
    factory = AgentFactory(
        app_config.brain,
        prompts,
        risk_config=app_config.risk,
        tier_registry=load_tier_registry(),
    )
    return TrendEntryGate(
        factory.create_trend_gate_agent(),
        prompts,
        app_config.strategy.trend_following.gate,
        factory.trend_gate_system_prompt(),
    )
