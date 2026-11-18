from pathlib import Path

import click

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


def _read_symbols_file(
    _ctx: click.Context, _param: click.Parameter, value: Path | None
) -> list[str] | None:
    """One symbol per line; blank lines and ``#`` comments are skipped."""
    if value is None:
        return None
    lines = value.read_text(encoding="utf-8").splitlines()
    symbols = [s.split("#", 1)[0].strip().upper() for s in lines]
    symbols = [s for s in symbols if s]
    if not symbols:
        raise click.BadParameter(f"{value} lists no symbols")
    return symbols


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
    callback=_read_symbols_file,
    help="File with one symbol per line; an alternative to --symbols.",
)


def resolve_symbols(
    symbols: list[str] | None, from_file: list[str] | None, default: list[str]
) -> list[str]:
    if symbols is not None and from_file is not None:
        msg = "give --symbols or --symbols-file, not both"
        raise click.UsageError(msg)
    return symbols or from_file or default
