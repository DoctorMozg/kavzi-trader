from datetime import UTC, datetime
from pathlib import Path

import click
import pandas as pd

from kavzi_trader.cli.commands.eval_options import (
    FRESH_UNIVERSE_FILE,
    SYMBOLS_FILE_OPTION,
    SYMBOLS_OPTION,
    TREND_BUFFER_BAND,
    TREND_TRADING_SYMBOLS,
    read_symbols_file,
    resolve_symbols,
)
from kavzi_trader.cli.commands.trend_ablation import load_trend_data, window_options
from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.intraday_data_loader import IntradayDataLoader
from kavzi_trader.evals.timing_arm_schema import TIMING_ARMS
from kavzi_trader.evals.timing_report_renderer import TimingReportRenderer
from kavzi_trader.evals.timing_scorer import TimingScorer
from kavzi_trader.evals.timing_verdict import TimingVerdict
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema


@click.command("trend-timing")
@click.option("--universe", type=click.Choice(["fresh", "trading"]), required=True)
@window_options
@click.option("--prereg", default=None, help="Preregistration file the report cites.")
@click.option("--out", type=click.Path(path_type=Path, dir_okay=False), default=None)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def trend_timing_command(
    ctx: click.Context,
    universe: str,
    archive_dir: Path,
    start_day: datetime,
    end_day: datetime,
    prereg: str | None,
    out: Path | None,
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Score the six timing arms of the trend rule against the daily rule."""
    app_config: AppConfig = ctx.obj["app_config"]
    fee = float(app_config.paper.commission_rate)
    default = (
        read_symbols_file(FRESH_UNIVERSE_FILE)
        if universe == "fresh"
        else TREND_TRADING_SYMBOLS
    )
    names = resolve_symbols(symbols, symbols_file, default)
    data = load_trend_data(archive_dir, names)
    loader = IntradayDataLoader(ArchiveSeries(archive_dir))
    try:
        intraday = loader.load(
            names, data.closes, sorted({arm.hours for arm in TIMING_ARMS})
        )
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    verdict = TimingVerdict()
    scorer = TimingScorer(
        TrendParamsSchema(lookbacks=(20,)),
        TREND_BUFFER_BAND,
        fee,
        TrendMetrics(CashRate.from_csv()),
        verdict,
    )
    try:
        run = scorer.run(
            universe,
            data,
            intraday,
            pd.Timestamp(start_day),
            pd.Timestamp(end_day) - pd.Timedelta(days=1),
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    report = TimingReportRenderer(verdict, prereg).render(run)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"trend_timing_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    click.echo(f"base: Sharpe {run.base.result.net.sharpe:.3f}")
    for outcome in run.arms:
        paired, adjusted = outcome.paired, outcome.adjusted
        click.echo(
            f"{outcome.arm.label}: Sharpe {paired.arm_sharpe:.3f} "
            f"(diff {paired.difference:+.3f}, 90% [{paired.lower:+.3f}, "
            f"{paired.upper:+.3f}], adjusted [{adjusted.lower:+.3f}, "
            f"{adjusted.upper:+.3f}])"
        )
    if run.reproduction_error:
        click.echo(f"VOID: {run.reproduction_error}")
    if run.quality_error:
        click.echo(f"VOID: {run.quality_error}")
    click.echo(f"Report: {path}")
    registry = TrialRegistry(trials_path(app_config))
    for outcome in run.arms:
        result = outcome.scored.result
        trial = TrialSchema(
            family="trend",
            variant=(
                f"timing {outcome.arm.label} lookbacks=20 mid-exit "
                f"symbols={','.join(result.symbols)} fee={fee} band={TREND_BUFFER_BAND}"
            ),
            first_day=result.first_day,
            last_day=result.last_day,
            daily_net=result.daily_net,
        )
        if registry.record(trial):
            click.echo(f"Trial registered: {outcome.arm.label}")
