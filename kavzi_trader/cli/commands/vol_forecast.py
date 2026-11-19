import asyncio
from datetime import UTC, datetime
from pathlib import Path

import click
import httpx2
import numpy as np
import pandas as pd

from kavzi_trader.cli.commands.eval_options import (
    SYMBOLS_FILE_OPTION,
    SYMBOLS_OPTION,
    TREND_BUFFER_BAND,
    TREND_TRADING_SYMBOLS,
    resolve_symbols,
)
from kavzi_trader.cli.commands.trend_ablation import (
    load_trend_data,
    run_backtest,
    window_options,
)
from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.ablation_report_renderer import AblationReportRenderer
from kavzi_trader.evals.dvol_history import DVOL_DIR, DvolHistory
from kavzi_trader.evals.forecast_vol_trend_signal import ForecastVolTrendSignal
from kavzi_trader.evals.har_vol_forecaster import HarVolForecaster
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.realized_variance import RealizedVariance
from kavzi_trader.evals.rolling_vol_forecaster import RollingVolForecaster
from kavzi_trader.evals.trend_data_schema import TrendDataSchema
from kavzi_trader.evals.validation.paired_sharpe_test import PairedSharpeTest
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.evals.vol_forecast_evaluator import VolForecastEvaluator
from kavzi_trader.evals.vol_forecast_score_schema import VolForecastScoreSchema
from kavzi_trader.evals.vol_forecaster import VolForecaster
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema

DVOL_CURRENCIES = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
# A forecaster goes on to the trading test only if it beats the rule's estimate.
MAX_P_VALUE = 0.05
TRADING_CANDIDATES = ("har", "lgbm", "chronos-2")


@click.command("dvol-download")
@click.option(
    "--from",
    "start_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default="2021-01-01",
    show_default=True,
)
@click.option(
    "--to", "end_day", type=click.DateTime(formats=["%Y-%m-%d"]), required=True
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DVOL_DIR,
    show_default=True,
)
def dvol_download_command(
    start_day: datetime, end_day: datetime, out_dir: Path
) -> None:
    """Download Deribit's daily BTC and ETH DVOL history to CSV."""

    async def _run() -> None:
        async with httpx2.AsyncClient(timeout=30.0) as http:
            history = DvolHistory(http)
            for currency in sorted(set(DVOL_CURRENCIES.values())):
                series = await history.download(
                    currency,
                    int(start_day.replace(tzinfo=UTC).timestamp() * 1000),
                    int(end_day.replace(tzinfo=UTC).timestamp() * 1000),
                )
                path = DvolHistory.save(series, out_dir)
                click.echo(
                    f"{currency}: {len(series)} days {series.index[0].date()} to "
                    f"{series.index[-1].date()}, {path}"
                )

    asyncio.run(_run())


def dvol_covariate(dvol_dir: Path, returns: pd.DataFrame) -> pd.DataFrame:
    """log of DVOL as annualised variance, for the symbols Deribit quotes."""
    frame = pd.DataFrame(np.nan, index=returns.index, columns=returns.columns)
    for symbol, currency in DVOL_CURRENCIES.items():
        if symbol in frame.columns:
            dvol = DvolHistory.load(currency, dvol_dir).reindex(returns.index)
            frame[symbol] = np.log((dvol / 100) ** 2)
    return frame


def _score_rows(scores: list[VolForecastScoreSchema]) -> list[list[str]]:
    return [
        [
            s.name,
            s.baseline,
            str(len(s.symbols)),
            str(s.days),
            Md.num(s.mean_qlike, 4),
            Md.num(s.baseline_qlike, 4),
            Md.num(s.dm_stat),
            Md.num(s.p_value, 4),
        ]
        for s in scores
    ]


def pick_winner(scores: list[VolForecastScoreSchema]) -> VolForecastScoreSchema | None:
    """Lowest-loss candidate that beats the rule's estimate at p < 0.05."""
    eligible = [
        s
        for s in scores
        if s.name in TRADING_CANDIDATES
        and s.p_value is not None
        and s.p_value < MAX_P_VALUE
        and s.mean_qlike < s.baseline_qlike
    ]
    return min(eligible, key=lambda s: s.mean_qlike, default=None)


@click.command("vol-forecast")
@click.option(
    "--chronos-revision",
    required=True,
    help="Pinned Hugging Face revision of amazon/chronos-2.",
)
@click.option(
    "--dvol-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DVOL_DIR,
    show_default=True,
)
@window_options
@click.option("--prereg", default=None, help="Preregistration file the report cites.")
@click.option("--out", type=click.Path(path_type=Path, dir_okay=False), default=None)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def vol_forecast_command(
    ctx: click.Context,
    chronos_revision: str,
    dvol_dir: Path,
    archive_dir: Path,
    start_day: datetime,
    end_day: datetime,
    prereg: str | None,
    out: Path | None,
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Score 7-day vol forecasts by QLIKE, then trade the best one in the trend rule."""
    # torch and LightGBM load here, not at CLI start, so `trade start` stays lean.
    from kavzi_trader.evals.chronos_vol_forecaster import ChronosVolForecaster
    from kavzi_trader.evals.lgbm_vol_forecaster import LgbmVolForecaster

    app_config: AppConfig = ctx.obj["app_config"]
    data = load_trend_data(
        archive_dir, resolve_symbols(symbols, symbols_file, TREND_TRADING_SYMBOLS)
    )
    first = pd.Timestamp(start_day)
    returns = RealizedVariance.log_returns(data.closes)
    realized = RealizedVariance.forward(returns)
    last_target_day = pd.Timestamp(end_day) - pd.Timedelta(days=1)
    in_window = (returns.index >= first) & (
        returns.index + pd.Timedelta(days=7) <= last_target_day
    )
    days = returns.index[in_window]
    covariate = {"log_dvol_var": dvol_covariate(dvol_dir, returns)}
    baseline = RollingVolForecaster()
    forecasters: list[VolForecaster] = [
        HarVolForecaster(first),
        HarVolForecaster(first, covariate, label="har-dvol"),
        LgbmVolForecaster(first),
        ChronosVolForecaster(first, chronos_revision),
    ]
    base_forecast = baseline.forecast(returns)
    forecasts = {f.name: f.forecast(returns) for f in forecasters}
    evaluator = VolForecastEvaluator(realized, days)
    scores = [
        evaluator.score(forecasts[name], base_forecast, name, baseline.name)
        for name in forecasts
    ]
    scores.append(
        evaluator.score(forecasts["har-dvol"], forecasts["har"], "har-dvol", "har")
    )
    for s in scores:
        click.echo(
            f"{s.name} vs {s.baseline}: QLIKE {s.mean_qlike:.4f} vs "
            f"{s.baseline_qlike:.4f}, DM {Md.num(s.dm_stat)}, p {Md.num(s.p_value, 4)}"
        )
    headers = [
        "Forecaster",
        "Against",
        "Symbols",
        "Days",
        "QLIKE",
        "Against QLIKE",
        "DM",
        "p",
    ]
    blocks = [
        "# Volatility forecasts for trend sizing",
        (
            f"{len(data.closes.columns)} symbols; forecasts at closes "
            f"{days[0].date()} to {days[-1].date()} of the next 7 days' realized "
            f"variance. "
            + (
                f"Rules: evals/preregistrations/{prereg}."
                if prereg
                else "Exploratory: no preregistration decides on this run."
            )
        ),
        Md.section(
            "Forecast accuracy (stage A)", Md.table(headers, _score_rows(scores))
        ),
    ]
    winner = pick_winner(scores)
    if winner is None:
        decision = "No candidate beat the rule's estimate at p < 0.05: stage B not run."
        blocks.append(Md.section("Trading test (stage B)", decision))
        click.echo(decision)
    else:
        blocks.append(
            _trade(
                app_config,
                data,
                forecasts[winner.name],
                winner.name,
                (start_day, end_day),
            )
        )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"vol_forecast_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    click.echo(f"Report: {path}")


def _trade(
    app_config: AppConfig,
    data: TrendDataSchema,
    variance: pd.DataFrame,
    name: str,
    window: tuple[datetime, datetime],
) -> str:
    fee = float(app_config.paper.commission_rate)
    params = TrendParamsSchema(lookbacks=(20,))
    base = run_backtest(DonchianTrendSignal(params), data, window, fee)
    arm = run_backtest(ForecastVolTrendSignal(params, variance), data, window, fee)
    paired = PairedSharpeTest().compare(base.daily_net, arm.daily_net)
    verdict = "ADOPT" if paired.lower > 0 else "KEEP the rolling estimate"
    click.echo(
        f"stage B {name}: Sharpe {paired.base_sharpe:.3f} -> {paired.arm_sharpe:.3f}, "
        f"90% [{paired.lower:+.3f}, {paired.upper:+.3f}]: {verdict}"
    )
    TrialRegistry(trials_path(app_config)).record(
        TrialSchema(
            family="trend",
            variant=(
                f"vol-forecast {name} lookbacks=20 symbols={','.join(arm.symbols)} "
                f"fee={fee} band={TREND_BUFFER_BAND}"
            ),
            first_day=arm.first_day,
            last_day=arm.last_day,
            daily_net=arm.daily_net,
        )
    )
    intro = (
        f"Decision: {verdict}. Base: Donchian long/flat lookbacks=20 sized by "
        f"30-day rolling vol. Arm: the same rule sized by the {name} forecast."
    )
    return Md.section(
        "Trading test (stage B)",
        intro,
        *AblationReportRenderer.sections(base, arm, paired),
    )
