from datetime import UTC, datetime
from pathlib import Path

import click

from kavzi_trader.api.binance.constants import KLINE_INTERVALS

MS_PER_S = 1000
S_PER_MIN = 60
INTERVAL_CHOICE = click.Choice(list(KLINE_INTERVALS))

TREND_TRADING_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
]
TREND_BUFFER_BAND = 0.2
FRESH_UNIVERSE_FILE = Path("evals/universes/fresh_2022.txt")


def day_start_ms(day: datetime | None) -> int:
    """Midnight UTC of ``day`` (default: today), so same-day reruns agree."""
    moment = day or datetime.now(UTC)
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    return int(midnight.timestamp() * MS_PER_S)


def parse_lookbacks(
    _ctx: click.Context, _param: click.Parameter, value: str
) -> tuple[int, ...]:
    try:
        return tuple(int(v) for v in value.split(","))
    except ValueError as exc:
        raise click.BadParameter("use comma-separated integers") from exc


def _parse_symbols(
    _ctx: click.Context, _param: click.Parameter, value: str | None
) -> list[str] | None:
    if value is None:
        return None
    symbols = [s.strip().upper() for s in value.split(",") if s.strip()]
    if not symbols:
        raise click.BadParameter("give at least one symbol")
    return symbols


def read_symbols_file(path: Path) -> list[str]:
    """One symbol per line; blank lines and ``#`` comments are skipped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    symbols = [s.split("#", 1)[0].strip().upper() for s in lines]
    symbols = [s for s in symbols if s]
    if not symbols:
        raise click.BadParameter(f"{path} lists no symbols")
    return symbols


def _read_symbols_option(
    _ctx: click.Context, _param: click.Parameter, value: Path | None
) -> list[str] | None:
    return None if value is None else read_symbols_file(value)


SYMBOLS_OPTION = click.option(
    "--symbols",
    default=None,
    callback=_parse_symbols,
    help="Comma-separated symbols; default the trading symbols.",
)

SYMBOLS_FILE_OPTION = click.option(
    "--symbols-file",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    default=None,
    callback=_read_symbols_option,
    help="File with one symbol per line; an alternative to --symbols.",
)


def resolve_symbols(
    symbols: list[str] | None, from_file: list[str] | None, default: list[str]
) -> list[str]:
    if symbols is not None and from_file is not None:
        msg = "give --symbols or --symbols-file, not both"
        raise click.UsageError(msg)
    return symbols or from_file or default
