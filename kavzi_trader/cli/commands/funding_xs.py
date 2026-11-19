from datetime import UTC, datetime
from pathlib import Path

import click

from kavzi_trader.cli.commands.eval_options import SYMBOLS_OPTION
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.funding_xs_backtester import FundingXsBacktester
from kavzi_trader.evals.funding_xs_loader import UNIVERSE, FundingXsLoader
from kavzi_trader.evals.funding_xs_metrics import FundingXsMetrics
from kavzi_trader.evals.funding_xs_params_schema import FundingXsParamsSchema
from kavzi_trader.evals.funding_xs_report_renderer import FundingXsReportRenderer


@click.command("funding-xs")
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
def funding_xs_command(
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
