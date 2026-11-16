from pathlib import Path

import click

from kavzi_trader.config import AppConfig
from kavzi_trader.evals.validation.backtest_overfitting import BacktestOverfitting
from kavzi_trader.evals.validation.sharpe_deflation import SharpeDeflation
from kavzi_trader.evals.validation.trial_analyzer import TrialAnalyzer
from kavzi_trader.evals.validation.trial_registry import TrialRegistry


def trials_path(app_config: AppConfig) -> Path:
    return app_config.system.results_dir / "evals" / "trials.jsonl"


@click.command("trials")
@click.option("--family", default="trend", show_default=True)
@click.option(
    "--blocks",
    type=click.IntRange(min=2),
    default=16,
    show_default=True,
    help="CSCV blocks for PBO; must be even.",
)
@click.pass_context
def trials_command(ctx: click.Context, family: str, blocks: int) -> None:
    """Deflate a family's best backtest by every variant tried, and its PBO."""
    app_config: AppConfig = ctx.obj["app_config"]
    path = trials_path(app_config)
    trials = TrialRegistry(path).trials(family)
    if not trials:
        raise click.ClickException(f"no {family!r} trials in {path}")
    try:
        analyzer = TrialAnalyzer(SharpeDeflation(), BacktestOverfitting(blocks))
        summary = analyzer.summarize(trials)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    deflated = summary.deflated
    click.echo(f"{summary.n_trials} {family} trials; best: {summary.best_variant}")
    click.echo(
        f"daily Sharpe {deflated.sharpe:.4f} vs {deflated.expected_max_sharpe:.4f} "
        f"expected from luck; deflated Sharpe {deflated.deflated_sharpe:.3f} "
        "(0.95 is the usual bar)"
    )
    if summary.pbo is None:
        click.echo("PBO: n/a (needs two trials over the best one's window)")
    else:
        click.echo(
            f"PBO {summary.pbo.pbo:.3f} over {summary.pbo_trials} trials and "
            f"{summary.pbo.n_combinations} CSCV splits"
        )
