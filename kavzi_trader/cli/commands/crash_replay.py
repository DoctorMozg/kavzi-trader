from datetime import UTC, datetime
from pathlib import Path

import click
import pandas as pd

from kavzi_trader.cli.commands.eval_options import (
    SYMBOLS_FILE_OPTION,
    SYMBOLS_OPTION,
    TREND_BUFFER_BAND,
    TREND_TRADING_SYMBOLS,
    resolve_symbols,
)
from kavzi_trader.cli.commands.trend_ablation import load_trend_data, window_options
from kavzi_trader.cli.commands.trials import trials_path
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.cash_rate import CashRate
from kavzi_trader.evals.crash_replay import CrashReplay
from kavzi_trader.evals.crash_replay_result_schema import CrashReplayResultSchema
from kavzi_trader.evals.markdown_format import Md
from kavzi_trader.evals.replay_variant_schema import ReplayVariantSchema
from kavzi_trader.evals.stop_fill_schema import StopFillSchema
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.validation.paired_sharpe_test import PairedSharpeTest
from kavzi_trader.evals.validation.trial_registry import TrialRegistry
from kavzi_trader.evals.validation.trial_schema import TrialSchema
from kavzi_trader.evals.vol_spike_halving import HOUR, HOUR_MS, VolSpikeHalving
from kavzi_trader.evals.weight_backtest import WeightBacktest
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

DAY_MS = 86_400_000
DISASTER_STOP_PCT = 0.3
# Most the halving rule may cost over the full window to be adopted.
MAX_SHARPE_COST = 0.05
AS_LIVE = "as live: last-price stop"
MARK_STOP = "mark-price stop"
HALVED = "as live + vol-spike halving"


def _rows(results: list[CrashReplayResultSchema]) -> list[list[str]]:
    return [
        [
            r.name,
            f"{100 * r.end_return:+.2f}%",
            f"{100 * r.worst_return:+.2f}%",
            r.worst_minute,
            "; ".join(s.describe() for s in r.stops) or "none",
        ]
        for r in results
    ]


def _replay_minutes(
    archive: ArchiveSeries, symbol: str, day: pd.Timestamp
) -> pd.DataFrame:
    """The day's 1m bars with the mark-price low beside each minute."""
    start_ms = int(day.timestamp() * 1000)
    bars = archive.minutes(symbol, ["low", "close"])
    today = bars[bars["open_time_ms"].between(start_ms, start_ms + DAY_MS - 1)]
    marks = archive.minutes(symbol, ["low"], mark=True).rename(
        columns={"low": "mark_low"}
    )
    return today.merge(marks, on="open_time_ms", how="left").ffill()


def _wick_stops(
    live: CrashReplayResultSchema,
    mark: CrashReplayResultSchema,
    day_return: dict[str, float],
) -> list[StopFillSchema]:
    """Last-price stops the mark price would not have fired, filled below the close."""
    marked = {s.symbol for s in mark.stops}
    return [
        s
        for s in live.stops
        if s.symbol not in marked and s.fill_return < day_return[s.symbol]
    ]


@click.command("crash-replay")
@click.option(
    "--day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default="2025-10-10",
    show_default=True,
    help="UTC day to replay minute by minute.",
)
@window_options
@click.option("--prereg", default=None, help="Preregistration file the report cites.")
@click.option("--out", type=click.Path(path_type=Path, dir_okay=False), default=None)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def crash_replay_command(
    ctx: click.Context,
    day: datetime,
    archive_dir: Path,
    start_day: datetime,
    end_day: datetime,
    prereg: str | None,
    out: Path | None,
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Replay the paper book through a crash day; price the vol-spike halving rule."""
    app_config: AppConfig = ctx.obj["app_config"]
    fee = float(app_config.paper.commission_rate)
    names = resolve_symbols(symbols, symbols_file, TREND_TRADING_SYMBOLS)
    data = load_trend_data(archive_dir, names)
    backtest = WeightBacktest(
        DonchianTrendSignal(TrendParamsSchema(lookbacks=(20,))),
        TurnoverBuffer(TREND_BUFFER_BAND),
        TrendPortfolio(fee),
        TrendMetrics(CashRate.from_csv()),
    )
    first, last = pd.Timestamp(start_day), pd.Timestamp(end_day) - pd.Timedelta(days=1)
    held = backtest.held_weights(data, first, last)
    replay_day = pd.Timestamp(day)
    book = {s: float(held.loc[replay_day, s]) for s in names}
    prev_close = {
        s: float(data.closes.loc[replay_day - pd.Timedelta(days=1), s]) for s in names
    }
    day_return = {
        s: float(data.closes.loc[replay_day, s]) / prev_close[s] - 1 for s in names
    }
    halving = VolSpikeHalving()
    archive = ArchiveSeries(archive_dir)
    triggers = {s: halving.triggers(archive.minutes(s, ["close"])) for s in names}
    minutes = {s: _replay_minutes(archive, s, replay_day) for s in names}
    halve_from = {
        s: int(t.loc[replay_day, HOUR].timestamp() * 1000) + HOUR_MS
        for s, t in triggers.items()
        if replay_day in t.index
    }
    variants = [
        ReplayVariantSchema(name="no stop", trigger="none"),
        ReplayVariantSchema(name=AS_LIVE, trigger="contract"),
        ReplayVariantSchema(name=MARK_STOP, trigger="mark"),
        ReplayVariantSchema(name=HALVED, trigger="contract", halve_from_ms=halve_from),
        ReplayVariantSchema(
            name="last-price stop, filled at the stop", trigger="contract", fill="stop"
        ),
    ]
    replay = CrashReplay(DISASTER_STOP_PCT, fee)
    results = {v.name: replay.run(book, prev_close, minutes, v) for v in variants}

    base = backtest.run(data, first, last)
    change = halving.adjustments(held, data.closes, triggers, fee)
    arm_net = (pd.Series(base.daily_net, index=held.index) + change).tolist()
    paired = PairedSharpeTest().compare(base.daily_net, arm_net)
    cost = paired.base_sharpe - paired.arm_sharpe
    adopt = (
        results[HALVED].end_return > results[AS_LIVE].end_return
        and cost <= MAX_SHARPE_COST
    )
    wicks = _wick_stops(results[AS_LIVE], results[MARK_STOP], day_return)
    halving_verdict = "ADOPT" if adopt else "REJECT"
    trigger_verdict = (
        "switch stops to MARK_PRICE" if wicks else "keep the last-price trigger"
    )
    TrialRegistry(trials_path(app_config)).record(
        TrialSchema(
            family="trend",
            variant=(
                f"vol-spike halving lookbacks=20 symbols={','.join(names)} "
                f"fee={fee} band={TREND_BUFFER_BAND}"
            ),
            first_day=base.first_day,
            last_day=base.last_day,
            daily_net=arm_net,
        )
    )
    spikes = sum(
        int(((t.index >= first) & (t.index <= last)).sum()) for t in triggers.values()
    )
    held_text = ", ".join(f"{s} {w:.3f}" for s, w in book.items() if w)
    rules = (
        f"Rules: evals/preregistrations/{prereg}."
        if prereg
        else "Exploratory: no preregistration decides on this run."
    )
    wick_text = "; ".join(w.describe() for w in wicks)
    blocks = [
        f"# Crash replay {replay_day.date()}",
        (
            "Paper rule (Donchian L20, 25% vol target, 2x cap, 30% disaster stop) "
            f"on {', '.join(names)}. {rules}"
        ),
        Md.section(
            "Book held into the day",
            held_text or "Flat: the rule held nothing, so the crash cost nothing.",
        ),
        Md.section(
            "Replay",
            Md.table(
                ["Variant", "Day return", "Worst minute return", "At", "Stops"],
                _rows(list(results.values())),
            ),
        ),
        Md.section(
            "Vol-spike halving over the full window",
            (
                f"{base.first_day} to {base.last_day}: {spikes} symbol-days with a "
                f"spike. Sharpe {paired.base_sharpe:.3f} -> {paired.arm_sharpe:.3f} "
                f"(cost {cost:+.3f}; 90% interval of the change "
                f"[{paired.lower:+.3f}, {paired.upper:+.3f}])."
            ),
        ),
        Md.section(
            "Decisions",
            (
                f"Halving: {halving_verdict} (needs a smaller replay loss than as "
                f"live and a Sharpe cost of at most {MAX_SHARPE_COST}). Stop "
                f"trigger: {trigger_verdict}"
                + (f" ({wick_text} fired below the day's close)." if wicks else ".")
            ),
        ),
    ]
    click.echo(f"Book: {held_text or 'flat'}")
    for r in results.values():
        click.echo(f"{r.name}: day {r.end_return:+.4f}, worst {r.worst_return:+.4f}")
    click.echo(f"Halving: cost {cost:+.3f}, {halving_verdict}; {trigger_verdict}")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"crash_replay_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    click.echo(f"Report: {path}")
