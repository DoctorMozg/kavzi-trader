from collections.abc import Callable
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
from kavzi_trader.evals.ablation_report_renderer import AblationReportRenderer
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.funding_crowding_overlay import FundingCrowdingOverlay
from kavzi_trader.evals.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.trend_result_schema import TrendResultSchema
from kavzi_trader.evals.validation.paired_sharpe_test import PairedSharpeTest
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.evals.weight_backtest import FIRST_RETURN_DAY, WeightBacktest
from kavzi_trader.evals.weight_signal import WeightSignal
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

# Last complete month in the archive when these tests were registered.
ABLATION_END_DAY = "2026-11-01"
_FAST_LOOKBACK = 10
ARMS = {
    "funding-crowding": (
        "halve long weight while 7d mean funding is in its 1y top decile"
    ),
    "mid-exit": "exit below the channel midpoint instead of the channel low",
    "fast-10": "add a 10-day Donchian lookback to the ensemble",
}


def arm_signal(
    arm: str, params: TrendParamsSchema, data: TrendDataSchema
) -> WeightSignal:
    if arm == "funding-crowding":
        return FundingCrowdingOverlay(DonchianTrendSignal(params), data.funding)
    if arm == "mid-exit":
        return MidExitTrendSignal(params)
    if arm == "fast-10":
        lookbacks = (_FAST_LOOKBACK, *params.lookbacks)
        return DonchianTrendSignal(params.model_copy(update={"lookbacks": lookbacks}))
    msg = f"unknown arm {arm!r}"
    raise ValueError(msg)


def run_backtest(
    signal: WeightSignal,
    data: TrendDataSchema,
    window: tuple[datetime, datetime],
    fee: float,
    band: float = TREND_BUFFER_BAND,
) -> TrendResultSchema:
    backtest = WeightBacktest(
        signal,
        TurnoverBuffer(band),
        TrendPortfolio(fee),
        TrendMetrics(CashRate.from_csv()),
    )
    start, end = window
    try:
        return backtest.run(
            data, pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(days=1)
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


def load_trend_data(archive_dir: Path, symbols: list[str]) -> TrendDataSchema:
    try:
        return TrendDataLoader(ArchiveSeries(archive_dir)).load(symbols)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc


def window_options[F: Callable[..., object]](func: F) -> F:
    """--archive-dir, --from and --to, shared by the trend comparison commands."""
    for option in (
        click.option(
            "--to",
            "end_day",
            type=click.DateTime(formats=["%Y-%m-%d"]),
            default=ABLATION_END_DAY,
            show_default=True,
            help="End of the scored window (UTC day, exclusive).",
        ),
        click.option(
            "--from",
            "start_day",
            type=click.DateTime(formats=["%Y-%m-%d"]),
            default=FIRST_RETURN_DAY.strftime("%Y-%m-%d"),
            show_default=True,
            help="First scored return day (UTC).",
        ),
        click.option(
            "--archive-dir",
            type=click.Path(path_type=Path, file_okay=False),
            default=Path("data/archive"),
            show_default=True,
        ),
    ):
        func = option(func)
    return func


@click.command("trend-ablation")
@click.option("--arm", type=click.Choice(list(ARMS)), required=True)
@click.option(
    "--lookbacks",
    default="20",
    show_default=True,
    callback=parse_lookbacks,
    help="Lookbacks of the base rule; 20 is the paper rule.",
)
@window_options
@click.option("--prereg", default=None, help="Preregistration file the report cites.")
@click.option("--out", type=click.Path(path_type=Path, dir_okay=False), default=None)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def trend_ablation_command(
    ctx: click.Context,
    arm: str,
    lookbacks: tuple[int, ...],
    archive_dir: Path,
    start_day: datetime,
    end_day: datetime,
    prereg: str | None,
    out: Path | None,
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Score one change to the paper trend rule against the rule, day by day."""
    app_config: AppConfig = ctx.obj["app_config"]
    fee = float(app_config.paper.commission_rate)
    params = TrendParamsSchema(lookbacks=lookbacks)
    data = load_trend_data(
        archive_dir, resolve_symbols(symbols, symbols_file, TREND_TRADING_SYMBOLS)
    )
    window = (start_day, end_day)
    base = run_backtest(DonchianTrendSignal(params), data, window, fee)
    arm_result = run_backtest(arm_signal(arm, params, data), data, window, fee)
    paired = PairedSharpeTest().compare(base.daily_net, arm_result.daily_net)
    base_label = f"Donchian long/flat lookbacks={','.join(map(str, lookbacks))}"
    report = AblationReportRenderer(base_label, f"{arm}: {ARMS[arm]}", prereg).render(
        base, arm_result, paired
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"ablation_{arm}_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    click.echo(
        f"{arm}: Sharpe {paired.base_sharpe:.3f} -> {paired.arm_sharpe:.3f} "
        f"(diff {paired.difference:+.3f}, 90% [{paired.lower:+.3f}, "
        f"{paired.upper:+.3f}]); max drawdown {base.net.max_drawdown:.1%} -> "
        f"{arm_result.net.max_drawdown:.1%}"
    )
    click.echo(f"Report: {path}")
    trial = TrialSchema(
        family="trend",
        variant=(
            f"ablation {arm} lookbacks={','.join(map(str, lookbacks))} "
            f"symbols={','.join(arm_result.symbols)} fee={fee} band={TREND_BUFFER_BAND}"
        ),
        first_day=arm_result.first_day,
        last_day=arm_result.last_day,
        daily_net=arm_result.daily_net,
    )
    if TrialRegistry(trials_path(app_config)).record(trial):
        click.echo("Trial registered")
