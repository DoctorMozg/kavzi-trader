from datetime import UTC, datetime
from pathlib import Path

import click

from kavzi_trader.cli.commands.eval_options import (
    SYMBOLS_FILE_OPTION,
    SYMBOLS_OPTION,
    TREND_TRADING_SYMBOLS,
    parse_lookbacks,
    resolve_symbols,
)
from kavzi_trader.cli.commands.trend_ablation import (
    load_trend_data,
    run_backtest,
    window_options,
)
from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema


def _floats(_ctx: click.Context, _param: click.Parameter, value: str) -> list[float]:
    try:
        return [float(v) for v in value.split(",")]
    except ValueError as exc:
        raise click.BadParameter("use comma-separated numbers") from exc


@click.command("buffer-sweep")
@click.option(
    "--bands", default="0,0.05,0.1,0.2,0.3,0.5", show_default=True, callback=_floats
)
@click.option(
    "--cost-multipliers",
    default="1,2,3",
    show_default=True,
    callback=_floats,
    help="Multiples of the configured commission rate.",
)
@click.option("--lookbacks", default="20", show_default=True, callback=parse_lookbacks)
@window_options
@click.option("--prereg", default=None, help="Preregistration file the report cites.")
@click.option("--out", type=click.Path(path_type=Path, dir_okay=False), default=None)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def buffer_sweep_command(
    ctx: click.Context,
    bands: list[float],
    cost_multipliers: list[float],
    lookbacks: tuple[int, ...],
    archive_dir: Path,
    start_day: datetime,
    end_day: datetime,
    prereg: str | None,
    out: Path | None,
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Net Sharpe and turnover of the trend rule per turnover band and fee level."""
    app_config: AppConfig = ctx.obj["app_config"]
    fee = float(app_config.paper.commission_rate)
    data = load_trend_data(
        archive_dir, resolve_symbols(symbols, symbols_file, TREND_TRADING_SYMBOLS)
    )
    signal = DonchianTrendSignal(TrendParamsSchema(lookbacks=lookbacks))
    registry = TrialRegistry(trials_path(app_config))
    sharpe_rows, turnover_rows = [], []
    first_day = last_day = ""
    for band in bands:
        sharpes, turnovers = [], []
        for multiplier in cost_multipliers:
            result = run_backtest(
                signal, data, (start_day, end_day), fee * multiplier, band
            )
            first_day, last_day = result.first_day, result.last_day
            sharpes.append(Md.num(result.net.sharpe, 3))
            turnovers.append(Md.num(result.turnover_per_year, 1))
            if multiplier == 1:
                registry.record(
                    TrialSchema(
                        family="trend",
                        variant=(
                            f"long-flat lookbacks={','.join(map(str, lookbacks))} "
                            f"symbols={','.join(result.symbols)} fee={fee} band={band}"
                        ),
                        first_day=result.first_day,
                        last_day=result.last_day,
                        daily_net=result.daily_net,
                    )
                )
        sharpe_rows.append([f"{band:g}", *sharpes])
        turnover_rows.append([f"{band:g}", *turnovers])
        click.echo(f"band {band:g}: net Sharpe {' / '.join(sharpes)}")
    headers = ["Band", *(f"fee x{m:g}" for m in cost_multipliers)]
    rules = (
        f"Rules: evals/preregistrations/{prereg}."
        if prereg
        else "Exploratory: no preregistration decides on this run."
    )
    report = "\n\n".join(
        [
            "# Turnover band sweep",
            (
                f"Donchian long/flat lookbacks={','.join(map(str, lookbacks))}, "
                f"{len(data.closes.columns)} symbols, {first_day} to {last_day}, "
                f"base fee {fee} per unit traded. {rules}"
            ),
            Md.section("Net Sharpe", Md.table(headers, sharpe_rows)),
            Md.section("Turnover per year (x NAV)", Md.table(headers, turnover_rows)),
        ]
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"buffer_sweep_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report + "\n", encoding="utf-8")
    click.echo(f"Report: {path}")
