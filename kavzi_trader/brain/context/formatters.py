from decimal import Decimal

from pydantic import BaseModel

from kavzi_trader.api.common.models import CandlestickSchema

_HEADER = "time|open|high|low|close|volume|quote_vol|trades|taker_buy_vol"
_HIGH_PRICE_THRESHOLD = 1000
_MID_PRICE_THRESHOLD = 1


def dump_json(model: BaseModel) -> str:
    return model.model_dump_json()


def dump_optional_json(model: BaseModel | None) -> str | None:
    if model is None:
        return None
    return model.model_dump_json()


def _fmt_price(value: Decimal, precision: int) -> str:
    return f"{float(value):.{precision}f}"


def _detect_price_precision(candles: list[CandlestickSchema]) -> int:
    if not candles:
        return 2
    sample = float(candles[0].close_price)
    if sample >= _HIGH_PRICE_THRESHOLD:
        return 2
    if sample >= _MID_PRICE_THRESHOLD:
        return 4
    return 6


def format_candles_table(candles: list[CandlestickSchema]) -> str:
    if not candles:
        return _HEADER
    precision = _detect_price_precision(candles)
    rows = [_HEADER]
    for c in candles:
        row = (
            f"{c.open_time.strftime('%H:%M')}"
            f"|{_fmt_price(c.open_price, precision)}"
            f"|{_fmt_price(c.high_price, precision)}"
            f"|{_fmt_price(c.low_price, precision)}"
            f"|{_fmt_price(c.close_price, precision)}"
            f"|{float(c.volume):.4f}"
            f"|{float(c.quote_volume):.2f}"
            f"|{c.trades_count}"
            f"|{float(c.taker_buy_base_volume):.4f}"
        )
        rows.append(row)
    return "\n".join(rows)
