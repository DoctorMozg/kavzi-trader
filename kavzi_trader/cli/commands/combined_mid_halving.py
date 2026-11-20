from datetime import UTC, datetime
from pathlib import Path

import click
import pandas as pd

from kavzi_trader.cli.commands.eval_options import (
    TREND_BUFFER_BAND,
    TREND_TRADING_SYMBOLS,
)
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.combined_arms_report_renderer import CombinedArmsReportRenderer
from kavzi_trader.evals.combined_arms_scorer import CombinedArmsScorer
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.evals.vol_spike_halving import VolSpikeHalving
from kavzi_trader.evals.weight_backtest import FIRST_RETURN_DAY
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.mid_exit_trend_signal import MidExitTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema

# Last complete month when the 2026-11-19 ablation and replay runs were scored.
END_DAY = "2026-11-01"


@click.command("combined-mid-halving")
@click.option(
    "--archive-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/archive"),
    show_default=True,
)
@click.option("--prereg", default=None, help="Preregistration file the report cites.")
@click.option("--out", type=click.Path(path_type=Path, dir_okay=False), default=None)
@click.pass_context
def combined_mid_halving_command(
    ctx: click.Context, archive_dir: Path, prereg: str | None, out: Path | None
) -> None:
    """Score mid exit and vol-spike halving, alone and together, on the trading 8."""
    app_config: AppConfig = ctx.obj["app_config"]
    fee = float(app_config.paper.commission_rate)
    params = TrendParamsSchema(lookbacks=(20,))
    archive = ArchiveSeries(archive_dir)
    try:
        data = TrendDataLoader(archive).load(TREND_TRADING_SYMBOLS)
        halving = VolSpikeHalving()
        triggers = {
            s: halving.triggers(archive.minutes(s, ["close"]))
            for s in TREND_TRADING_SYMBOLS
        }
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    scorer = CombinedArmsScorer(
        DonchianTrendSignal(params),
        MidExitTrendSignal(params),
        halving,
        TREND_BUFFER_BAND,
        fee,
        TrendMetrics(CashRate.from_csv()),
    )
    last_day = pd.Timestamp(END_DAY) - pd.Timedelta(days=1)
    result = scorer.run(data, triggers, FIRST_RETURN_DAY, last_day)
    report = CombinedArmsReportRenderer(prereg).render(result)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"combined_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    click.echo(report)
    click.echo(f"Report: {path}")
    arm = result.mid_halving
    TrialRegistry(app_config.system.results_dir / "evals" / "trials.jsonl").record(
        TrialSchema(
            family="trend",
            variant=(
                f"mid exit + vol-spike halving lookbacks=20 "
                f"symbols={','.join(arm.symbols)} fee={fee} band={TREND_BUFFER_BAND}"
            ),
            first_day=arm.first_day,
            last_day=arm.last_day,
            daily_net=arm.daily_net,
        )
    )
