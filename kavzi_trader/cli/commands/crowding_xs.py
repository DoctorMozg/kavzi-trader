from datetime import UTC, datetime
from pathlib import Path

import click
import pandas as pd

from kavzi_trader.cli.commands.eval_options import SYMBOLS_FILE_OPTION, SYMBOLS_OPTION
from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.crowding_xs_loader import CrowdingXsLoader
from kavzi_trader.evals.crowding_xs_signal import CrowdingXsSignal
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.market_alpha import MarketAlpha
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.evals.weight_backtest import WeightBacktest
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

# The alpha must be positive and this many Newey-West standard errors from zero.
MIN_ALPHA_T = 2.0


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


@click.command("crowding-xs")
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.option("--market", default="BTCUSDT", show_default=True, help="Beta reference.")
@click.option(
    "--history", type=int, default=1000, show_default=True, help="Rank window, 4h bars."
)
@click.option("--rebalance-days", type=int, default=7, show_default=True)
@click.option(
    "--from",
    "start_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default="2023-06-18",
    show_default=True,
    help="First scored return day (UTC); also the first rebalance.",
)
@click.option(
    "--to",
    "end_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default="2026-11-15",
    show_default=True,
    help="End of the scored window (UTC day, exclusive).",
)
@click.option("--prereg", default=None, help="Preregistration file the report cites.")
@click.option("--out", type=click.Path(path_type=Path, dir_okay=False), default=None)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def crowding_xs_command(
    ctx: click.Context,
    cache_dir: Path,
    market: str,
    history: int,
    rebalance_days: int,
    start_day: datetime,
    end_day: datetime,
    prereg: str | None,
    out: Path | None,
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Market-neutral ls_crowding: short the crowded third, long the least crowded."""
    app_config: AppConfig = ctx.obj["app_config"]
    names = symbols or symbols_file
    if not names:
        raise click.UsageError("give --symbols or --symbols-file")
    fee = float(app_config.paper.commission_rate)
    loader = CrowdingXsLoader(cache_dir, history)
    loaded = loader.load(names)
    data = loaded.market
    benchmark = loader.load([market]).market
    first, last = pd.Timestamp(start_day), pd.Timestamp(end_day) - pd.Timedelta(days=1)
    backtest = WeightBacktest(
        CrowdingXsSignal(loaded.ranks, first, rebalance_days),
        TurnoverBuffer(0.0),
        TrendPortfolio(fee),
        TrendMetrics(CashRate.from_csv()),
    )
    try:
        result = backtest.run(data, first, last)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    days = pd.date_range(result.first_day, result.last_day, freq="D")
    net = pd.Series(result.daily_net, index=days)
    alpha = MarketAlpha().regress(net, benchmark.closes[market].pct_change())
    passed = alpha.alpha_annual > 0 and alpha.alpha_t >= MIN_ALPHA_T
    verdict = "PASS" if passed else "FAIL"
    stats = result.net
    rows = [
        ["Net Sharpe", Md.num(stats.sharpe)],
        ["Sharpe over cash", Md.num(stats.sharpe_over_cash)],
        ["Net return (annualised)", _pct(stats.annual_return)],
        ["Volatility", _pct(stats.annual_vol)],
        ["Max drawdown", _pct(stats.max_drawdown)],
        ["Turnover per year (x NAV)", Md.num(result.turnover_per_year)],
        ["Cost drag per year", _pct(result.cost_drag)],
        ["Funding drag per year (negative: received)", _pct(result.funding_drag)],
        [f"Alpha vs {market} (annualised)", _pct(alpha.alpha_annual)],
        [f"Beta to {market}", Md.num(alpha.beta)],
        ["Alpha t (Newey-West, lag 5)", Md.num(alpha.alpha_t)],
    ]
    years = [[str(y), Md.num(v)] for y, v in sorted(stats.sharpe_by_year.items())]
    rules = (
        f"Rules: evals/preregistrations/{prereg}."
        if prereg
        else "Exploratory: no preregistration decides on this run."
    )
    report = "\n\n".join(
        [
            "# ls_crowding, market-neutral cross-section",
            (
                f"{len(data.closes.columns)} symbols, {result.first_day} to "
                f"{result.last_day}; rebalance every {rebalance_days} days, rank "
                f"window {history} 4h bars, fee {fee} per unit traded. {rules}"
            ),
            Md.section("Summary", Md.table(["", "Value"], rows)),
            Md.section("Sharpe by year", Md.table(["Year", "Sharpe"], years)),
            Md.section(
                "Decision",
                f"{verdict}: needs alpha > 0 with t >= {MIN_ALPHA_T}.",
            ),
        ]
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"crowding_xs_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report + "\n", encoding="utf-8")
    click.echo(
        f"Sharpe {Md.num(stats.sharpe)}, alpha {alpha.alpha_annual:+.1%} "
        f"(t {alpha.alpha_t:.2f}), beta {alpha.beta:.2f}: {verdict}"
    )
    click.echo(f"Report: {path}")
    TrialRegistry(trials_path(app_config)).record(
        TrialSchema(
            family="crowding-xs",
            variant=(
                f"thirds rebalance={rebalance_days}d history={history} "
                f"symbols={len(data.closes.columns)} fee={fee}"
            ),
            first_day=result.first_day,
            last_day=result.last_day,
            daily_net=result.daily_net,
        )
    )
