from datetime import UTC, datetime
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
from kavzi_trader.evals.cash_rate import CashRate
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
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

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


@click.command("trend")
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
def trend_command(
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
