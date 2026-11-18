import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
import pandas as pd

from kavzi_trader.cli.commands.eval_options import (
    SYMBOLS_FILE_OPTION,
    SYMBOLS_OPTION,
    TREND_BUFFER_BAND,
    TREND_TRADING_SYMBOLS,
    parse_lookbacks,
    resolve_symbols,
)
from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.date_window_schema import DateWindowSchema
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.evals.walk_forward import WalkForward
from kavzi_trader.evals.walk_forward_report_renderer import WalkForwardReportRenderer
from kavzi_trader.evals.weight_backtest import WeightBacktest
from kavzi_trader.evals.weight_signal import WeightSignal
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)

_DAY = click.DateTime(formats=["%Y-%m-%d"])


@click.command("trend-walkforward")
@click.option(
    "--lookbacks",
    default="10,20,30,40,60,80,120",
    show_default=True,
    callback=parse_lookbacks,
    help="Candidate Donchian lookbacks; each test year picks one.",
)
@click.option(
    "--hindsight-lookback",
    type=int,
    default=20,
    show_default=True,
    help="Fixed lookback reported alongside, for the hindsight gap.",
)
@click.option("--train-from", type=_DAY, default="2020-12-15", show_default=True)
@click.option("--test-from", type=_DAY, default="2022-01-01", show_default=True)
@click.option(
    "--to",
    "end_day",
    type=_DAY,
    default="2026-11-01",
    show_default=True,
    help="End of the last test year (UTC day, exclusive).",
)
@click.option(
    "--archive-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/archive"),
    show_default=True,
)
@click.option("--prereg", required=True, help="Preregistration file the report cites.")
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Report path; default results/evals/walkforward_<UTC time>.md.",
)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def walk_forward_command(
    ctx: click.Context,
    lookbacks: tuple[int, ...],
    hindsight_lookback: int,
    train_from: datetime,
    test_from: datetime,
    end_day: datetime,
    archive_dir: Path,
    prereg: str,
    out: Path | None,
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Pick the trend lookback each year from earlier years only, then score it."""
    app_config: AppConfig = ctx.obj["app_config"]
    names = resolve_symbols(symbols, symbols_file, TREND_TRADING_SYMBOLS)
    try:
        data = TrendDataLoader(ArchiveSeries(archive_dir)).load(names)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    buffer = TurnoverBuffer(TREND_BUFFER_BAND)
    portfolio = TrendPortfolio(float(app_config.paper.commission_rate))
    walk = WalkForward({lb: _signal(lb) for lb in lookbacks}, buffer, portfolio)
    span = DateWindowSchema(
        first_day=test_from.date(), last_day=end_day.date() - timedelta(days=1)
    )
    try:
        result = walk.run(data, train_from.date(), WalkForward.calendar_years(span))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    hindsight = WeightBacktest(_signal(hindsight_lookback), buffer, portfolio).run(
        data, pd.Timestamp(span.first_day), pd.Timestamp(span.last_day)
    )

    renderer = WalkForwardReportRenderer(prereg)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"walkforward_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(renderer.render(result, hindsight), encoding="utf-8")
    oos = result.out_of_sample
    click.echo(
        f"walk-forward net Sharpe {oos.net.sharpe}, benchmark {oos.benchmark.sharpe}, "
        f"criterion met: {renderer.criterion_met(result)}"
    )
    click.echo(f"Report: {path}")
    # Every variant tried counts against the best one in the deflated Sharpe.
    trial = TrialSchema(
        family="trend",
        variant=(
            f"walk-forward lookbacks={','.join(map(str, lookbacks))} "
            f"train_from={result.train_first_day} symbols={','.join(oos.symbols)} "
            f"fee={app_config.paper.commission_rate} band={TREND_BUFFER_BAND}"
        ),
        first_day=oos.first_day,
        last_day=oos.last_day,
        daily_net=oos.daily_net,
    )
    registry = TrialRegistry(trials_path(app_config))
    if registry.record(trial):
        click.echo(f"Trial registered; {len(registry.trials('trend'))} trend trials")


def _signal(lookback: int) -> WeightSignal:
    return DonchianTrendSignal(TrendParamsSchema(lookbacks=(lookback,)))
