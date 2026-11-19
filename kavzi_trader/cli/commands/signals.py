import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import click
import numpy as np
import pandas as pd
from pydantic import ValidationError

from kavzi_trader.api.binance.constants import KLINE_INTERVALS
from kavzi_trader.cli.commands.eval_options import (
    INTERVAL_CHOICE,
    MS_PER_S,
    S_PER_MIN,
    SYMBOLS_FILE_OPTION,
    SYMBOLS_OPTION,
    day_start_ms,
    resolve_symbols,
)
from kavzi_trader.cli.commands.market_data_loader import MarketDataLoader
from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.candidate_signals import (
    CANDIDATE_SIGNALS,
    LEADER_SYMBOL,
    CandidateSignals,
)
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.market_feature_builder import MarketFeatureBuilder
from kavzi_trader.evals.metrics_alignment import MetricsAlignment
from kavzi_trader.evals.positioning_signals import (
    POSITIONING_SIGNALS,
    PositioningSignals,
)
from kavzi_trader.evals.sample_window_schema import SampleWindowSchema
from kavzi_trader.evals.scout_signals import ScoutSignals
from kavzi_trader.evals.signal_bracket_schema import SignalBracketSchema
from kavzi_trader.evals.signal_edge_analyzer import SignalEdgeAnalyzer
from kavzi_trader.evals.signal_report_renderer import SignalReportRenderer
from kavzi_trader.evals.signal_sampler import (
    CANDLE_SIGNALS,
    FUNDING_SIGNAL,
    OI_SIGNALS,
    SIDES,
    SignalSampler,
)
from kavzi_trader.order_flow.calculator import OrderFlowCalculator


def _oi_grids(
    archive: dict[str, pd.DataFrame], order_flow: OrderFlowCalculator
) -> dict[str, pd.DataFrame]:
    """Metrics OI on the period grid the live OrderFlowCalculator indexes by."""
    period_ms = KLINE_INTERVALS[order_flow.oi_period] * MS_PER_S
    return {s: MetricsAlignment.oi_grid(m, period_ms) for s, m in archive.items()}


def _add_positioning(
    history: int,
    frames: dict[str, pd.DataFrame],
    parts: list[pd.DataFrame],
    archive: dict[str, pd.DataFrame],
) -> list[pd.DataFrame]:
    positioning = PositioningSignals(history)
    return [
        positioning.add(frames[s], p, archive[s])
        for s, p in zip(frames, parts, strict=True)
    ]


def _leader(cache: CandleCache, frames: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """BTC candles for the lead signal, from the cache when BTC is not sampled."""
    if LEADER_SYMBOL in frames:
        return frames[LEADER_SYMBOL]
    leader = cache.load(LEADER_SYMBOL).reset_index(drop=True)
    return None if leader.empty else leader


def _add_combos(
    samples: pd.DataFrame, combos: tuple[str, ...], signals: tuple[str, ...]
) -> None:
    """Add a LONG_/SHORT_ column per combo: every listed signal fires on that side."""
    for combo in combos:
        names = combo.split("+")
        unknown = [n for n in names if n not in signals]
        if len(names) < 2 or unknown:  # noqa: PLR2004 - a combo joins two or more
            msg = f"--combo {combo!r}: need 2+ scored signals, unknown {unknown}"
            raise click.BadParameter(msg)
        for side in SIDES:
            columns = [samples[f"{side}_{n}"].to_numpy(dtype=bool) for n in names]
            samples[f"{side}_{combo}"] = np.logical_and.reduce(columns)


def _parse_brackets(
    _ctx: click.Context, _param: click.Parameter, values: tuple[str, ...]
) -> list[SignalBracketSchema]:
    try:
        return [SignalBracketSchema.parse(v) for v in values]
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc


@click.command("signals")
@click.option(
    "--bracket",
    "brackets",
    multiple=True,
    default=("1.5:3:96",),
    show_default=True,
    callback=_parse_brackets,
    help="SL_ATR:TP_ATR:HORIZON_BARS; repeat to compare brackets.",
)
@click.option(
    "--stride",
    type=click.IntRange(min=1),
    default=17,
    show_default=True,
    # Volume is intraday-seasonal; a divisor of 96 would only sample a few
    # times of day (16 bars always hits the same 6 slots).
    help="Sample every Nth bar; keep it coprime with the bars per day.",
)
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
    help="Report path; default results/evals/signals_<UTC time>.md.",
)
@click.option(
    "--funding/--no-funding",
    default=False,
    help="Download funding history and score the live funding signal too.",
)
@click.option(
    "--oi/--no-oi",
    default=False,
    help=(
        "Also score the OI signals (implies --funding). Binance keeps about 30 "
        "days of OI, so only bars in that window are sampled."
    ),
)
@click.option(
    "--metrics/--no-metrics",
    default=False,
    help="Score OI and long/short flags from the 5-minute metrics archive, in "
    "place of openInterestHist (implies --funding; excludes --oi).",
)
@click.option(
    "--interval",
    type=INTERVAL_CHOICE,
    default=None,
    help="Candle interval to test; default the trading interval. Fill it with "
    "refresh-cache first.",
)
@click.option(
    "--from",
    "start_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Only sample bars closing on or after this UTC day; earlier bars still "
    "warm up the indicators.",
)
@click.option(
    "--to",
    "end_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Only sample bars closing before this UTC day (exclusive).",
)
@click.option(
    "--candidates/--no-candidates",
    default=False,
    help="Also score signals the bot does not use yet: taker flow, 1h trend, BTC lead.",
)
@click.option(
    "--scout-vol-min",
    "scout_vol_mins",
    type=click.FloatRange(min=0),
    multiple=True,
    help="Replay the live Scout with this trend_vol_ratio_min and score its "
    "TREND_CONTINUATION calls; repeat to compare thresholds.",
)
@click.option(
    "--combo",
    "combos",
    multiple=True,
    help="A+B: also score bars where all listed signals fire on the same side; "
    "repeatable.",
)
@SYMBOLS_OPTION
@SYMBOLS_FILE_OPTION
@click.pass_context
def signals_command(
    ctx: click.Context,
    brackets: list[SignalBracketSchema],
    stride: int,
    cache_dir: Path,
    out: Path | None,
    funding: bool,
    oi: bool,
    metrics: bool,
    interval: str | None,
    start_day: datetime | None,
    end_day: datetime | None,
    candidates: bool,
    scout_vol_mins: tuple[float, ...],
    combos: tuple[str, ...],
    symbols: list[str] | None,
    symbols_file: list[str] | None,
) -> None:
    """Measure each confluence signal's R edge on cached candles; no LLM calls."""
    if oi and metrics:
        raise click.UsageError("--oi and --metrics are alternative OI sources")
    app_config: AppConfig = ctx.obj["app_config"]
    history = app_config.trading.history_candles
    interval = interval or app_config.trading.interval
    cache = CandleCache(cache_dir, interval)
    names = resolve_symbols(symbols, symbols_file, app_config.trading.symbols)
    frames = {s: cache.load_traded(s) for s in names}
    frames = {s: f for s, f in frames.items() if not f.empty}
    if not frames:
        msg = (
            f"No cached {interval} candles in {cache_dir}; run "
            f"`eval refresh-cache --interval {interval}`"
        )
        raise click.ClickException(msg)
    order_flow = OrderFlowCalculator(KLINE_INTERVALS[interval] // S_PER_MIN)
    try:
        window = SampleWindowSchema(
            start_ms=None if start_day is None else day_start_ms(start_day),
            end_ms=None if end_day is None else day_start_ms(end_day),
        )
    except ValidationError as exc:
        raise click.BadParameter("--from must be before --to") from exc
    sampler = SignalSampler(
        MarketFeatureBuilder(app_config.risk), history, stride, order_flow, window
    )
    funding = funding or oi or metrics
    max_horizon = max(b.horizon_bars for b in brackets)
    loader = MarketDataLoader(cache_dir, ctx.obj.get("exchange_client"))
    settlements = loader.funding(frames) if funding else {}
    snapshots = loader.oi(frames, order_flow.oi_period) if oi else {}
    archive = loader.metrics(frames) if metrics else {}
    snapshots = _oi_grids(archive, order_flow) if metrics else snapshots
    parts = [
        sampler.sample(s, f, max_horizon, settlements.get(s), snapshots.get(s))
        for s, f in frames.items()
    ]
    if metrics:
        parts = _add_positioning(history, frames, parts, archive)
    if candidates:
        extra = CandidateSignals(history, _leader(cache, frames), htf=interval == "15m")
        parts = [extra.add(s, frames[s], p) for s, p in zip(frames, parts, strict=True)]
    scout = ScoutSignals(
        app_config,
        load_tier_registry(),
        interval,
        [Decimal(str(v)) for v in scout_vol_mins],
    )
    if scout_vol_mins:
        parts = [
            asyncio.run(scout.add(s, frames[s], p))
            for s, p in zip(frames, parts, strict=True)
        ]
    parts = [part for part in parts if not part.empty]
    if not parts:
        raise click.ClickException("No bars to sample; is the OI window covered?")
    samples = pd.concat(parts, ignore_index=True)
    signals: tuple[str, ...] = CANDLE_SIGNALS
    if funding:
        signals = (*signals, FUNDING_SIGNAL)
    if oi or metrics:
        signals = (*signals, *OI_SIGNALS, *(POSITIONING_SIGNALS if metrics else ()))
    if candidates:
        signals = (*signals, *[c for c in CANDIDATE_SIGNALS if f"LONG_{c}" in samples])
    signals = (*signals, *scout.names)
    _add_combos(samples, combos, signals)
    signals = (*signals, *combos)
    analyzer = SignalEdgeAnalyzer(
        stride, signals, float(app_config.paper.commission_rate)
    )
    results = [analyzer.analyze(samples, frames, b) for b in brackets]
    renderer = SignalReportRenderer(stride, history, list(frames), interval, window)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"signals_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(renderer.render(results), encoding="utf-8")
    for line in renderer.summary(results):
        click.echo(line)
    click.echo(f"Report: {path}")
