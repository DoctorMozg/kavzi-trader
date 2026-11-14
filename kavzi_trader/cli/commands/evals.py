"""Evaluation dataset commands for the KavziTrader CLI."""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import click

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.case_dataset_file import CaseDatasetFile
from kavzi_trader.evals.dataset_build_params_schema import DatasetBuildParamsSchema
from kavzi_trader.evals.dataset_builder import DatasetBuilder
from kavzi_trader.evals.distribution_report_schema import DistributionReportSchema

logger = logging.getLogger(__name__)

_MS_PER_S = 1000


def _day_start_ms(day: datetime | None) -> int:
    """Midnight UTC of ``day`` (default: today), so same-day reruns agree."""
    moment = day or datetime.now(UTC)
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    return int(midnight.timestamp() * _MS_PER_S)


def _echo_report(report: DistributionReportSchema) -> None:
    for name, value in report.model_dump().items():
        click.echo(f"{name}: {value}")


@click.group("eval")
def eval_group() -> None:
    """Evaluation suite commands."""


@eval_group.command("build-dataset")
@click.option(
    "--months",
    type=click.FloatRange(min=0, min_open=True),
    default=12.0,
    show_default=True,
)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--cases", type=click.IntRange(min=1), default=200, show_default=True)
@click.option(
    "--out",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("evals/cases_v1.jsonl"),
    show_default=True,
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("data/eval_cache"),
    show_default=True,
)
@click.option(
    "--end-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Exclusive UTC end of the data window; default today 00:00 UTC.",
)
@click.pass_context
def build_dataset(
    ctx: click.Context,
    months: float,
    seed: int,
    cases: int,
    out: Path,
    cache_dir: Path,
    end_date: datetime | None,
) -> None:
    """Download futures klines and write the frozen triple-barrier eval cases."""
    app_config: AppConfig = ctx.obj["app_config"]
    params = DatasetBuildParamsSchema(
        symbols=app_config.trading.symbols,
        interval=app_config.trading.interval,
        history_candles=app_config.trading.history_candles,
        max_hold_time_hours=app_config.position_management.max_hold_time_hours,
        months=months,
        cases=cases,
        seed=seed,
        data_end_ms=_day_start_ms(end_date),
        cache_dir=cache_dir,
    )

    async def _run() -> None:
        client = BinanceClient()  # public market data, no credentials
        try:
            builder = DatasetBuilder(
                params, app_config.risk, load_tier_registry(), client
            )
            result = await builder.build()
        finally:
            await client.close()
        CaseDatasetFile(out).write(result.cases)
        _echo_report(result.report)
        if any(result.report.shortfall_by_label.values()):
            logger.warning(
                "Dataset short of quota: %s", result.report.shortfall_by_label
            )

    asyncio.run(_run())
