import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import click
import pandas as pd
from pydantic import SecretStr

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.symbol_filters_loader import FuturesSymbolFiltersLoader
from kavzi_trader.cli.composition import build_agent_source
from kavzi_trader.cli.replay_composition import (
    REPLAY_STRATEGIES,
    ReplayComposer,
    replay_costs,
    replay_needs,
)
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.agent_source import AgentSource
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.evals.trend_stats_schema import TrendStatsSchema
from kavzi_trader.evals.weight_backtest import (
    FIRST_RETURN_DAY,
    LAST_RETURN_DAY,
    WeightBacktest,
)
from kavzi_trader.replay.llm_tape import LlmTape
from kavzi_trader.replay.replay_data_loader import ReplayDataLoader
from kavzi_trader.replay.replay_report_renderer import ReplayReportRenderer
from kavzi_trader.replay.replay_result_schema import ReplayResultSchema
from kavzi_trader.replay.replay_runner import ReplayRunner
from kavzi_trader.replay.taped_agent_source import TapedAgentSource
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

logger = logging.getLogger(__name__)


async def _load_precision(symbols: list[str]) -> SymbolPrecision:
    # exchangeInfo is public; today's filters stand in for historical ones.
    client = BinanceClient()
    try:
        return SymbolPrecision(await FuturesSymbolFiltersLoader(client).load(symbols))
    finally:
        await client.close()


async def _replay(
    app_config: AppConfig,
    strategy: str,
    cache_dir: Path,
    window: pd.DatetimeIndex,
    slippage_bps: Decimal,
    agents: TapedAgentSource | None,
) -> ReplayResultSchema:
    needs = replay_needs(app_config, strategy)
    data = ReplayDataLoader(cache_dir).load(needs)
    costs = replay_costs(app_config.paper.commission_rate, slippage_bps)
    precision = await _load_precision(needs.symbols)
    composer = ReplayComposer(app_config, precision, costs, agents)
    start_ms, end_ms = (int(day.value // 1_000_000) for day in window)
    rig = await composer.compose(strategy, data, start_ms)
    runner = ReplayRunner(rig, data)
    return await runner.run(start_ms, end_ms)


def _taped_agents(
    ctx: click.Context, app_config: AppConfig, tape_path: Path, *, record: bool
) -> TapedAgentSource:
    injected: AgentSource | None = ctx.obj.get("agent_source")
    if injected is not None:
        agents = injected
    elif record:
        agents = build_agent_source(app_config)
    else:
        # A replay-only run answers from the tape and never reaches a provider,
        # so a placeholder stands in for a missing key.
        brain = app_config.brain
        placeholder = SecretStr("replay-only")
        agents = build_agent_source(
            app_config.model_copy(
                update={
                    "brain": brain.model_copy(
                        update={
                            "anthropic_api_key": brain.anthropic_api_key
                            if brain.anthropic_api_key.get_secret_value()
                            else placeholder,
                            "openrouter_api_key": brain.openrouter_api_key
                            if brain.openrouter_api_key.get_secret_value()
                            else placeholder,
                        }
                    )
                }
            )
        )
    return TapedAgentSource(agents, LlmTape(tape_path), record=record)


def _vectorized_trend(
    app_config: AppConfig, cache_dir: Path, window: pd.DatetimeIndex
) -> TrendStatsSchema:
    trend = app_config.strategy.trend_following
    params = TrendParamsSchema(
        lookbacks=tuple(trend.lookbacks),
        vol_window=trend.vol_window,
        annual_vol_target=trend.annual_vol_target,
        max_leverage=trend.max_leverage,
    )
    backtest = WeightBacktest(
        DonchianTrendSignal(params),
        TurnoverBuffer(trend.buffer_band),
        TrendPortfolio(float(app_config.paper.commission_rate)),
    )
    data = TrendDataLoader(cache_dir).load(trend.symbols)
    return backtest.run(data, window[0], window[1] - pd.Timedelta(days=1)).net


@click.command("replay")
@click.option(
    "--strategy",
    type=click.Choice(REPLAY_STRATEGIES),
    default="trend_following",
    show_default=True,
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.option(
    "--from",
    "start_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=FIRST_RETURN_DAY.strftime("%Y-%m-%d"),
    show_default=True,
    help="First traded UTC day; earlier cached bars only warm up indicators.",
)
@click.option(
    "--to",
    "end_day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=(LAST_RETURN_DAY + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
    show_default=True,
    help="End of the replay (UTC day, exclusive).",
)
@click.option(
    "--slippage-bps",
    type=click.FloatRange(min=0),
    default=0.0,
    show_default=True,
    help="Adverse move on every taker fill.",
)
@click.option(
    "--tape",
    "tape_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("data/replay_tape.jsonl"),
    show_default=True,
    help="LLM response tape the llm_pipeline replay reads and records into.",
)
@click.option(
    "--record",
    is_flag=True,
    help="Call the LLM for requests missing from the tape (paid API calls).",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Report path; default results/evals/replay_<UTC time>.md.",
)
@click.pass_context
def replay_command(
    ctx: click.Context,
    strategy: str,
    cache_dir: Path,
    start_day: datetime,
    end_day: datetime,
    slippage_bps: float,
    tape_path: Path,
    record: bool,
    out: Path | None,
) -> None:
    """Replay a strategy through the live loops and spine on cached history."""
    app_config: AppConfig = ctx.obj["app_config"]
    window = pd.DatetimeIndex([pd.Timestamp(start_day), pd.Timestamp(end_day)])
    agents = None
    if strategy == "llm_pipeline":
        agents = _taped_agents(ctx, app_config, tape_path, record=record)
        if record:
            click.echo("Recording: tape misses call the LLM API and cost money.")
    try:
        result = asyncio.run(
            _replay(
                app_config,
                strategy,
                cache_dir,
                window,
                Decimal(str(slippage_bps)),
                agents,
            )
        )
        reference = (
            _vectorized_trend(app_config, cache_dir, window)
            if strategy == "trend_following"
            else None
        )
    except (ValueError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc)) from exc
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out or app_config.system.results_dir / "evals" / f"replay_{stamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ReplayReportRenderer().render(result, reference), encoding="utf-8")
    vectorized = f", vectorized {reference.sharpe}" if reference else ""
    click.echo(
        f"replay Sharpe {result.stats.sharpe}{vectorized}, "
        f"equity {result.initial_equity:.2f} -> {result.final_equity:.2f}"
    )
    click.echo(f"Report: {path}")
    if result.llm is not None and result.llm.tape_misses:
        msg = (
            f"{result.llm.tape_misses} LLM requests were not on the tape {tape_path}; "
            "rerun with --record to fill it"
        )
        raise click.ClickException(msg)
