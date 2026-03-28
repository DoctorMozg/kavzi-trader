from decimal import Decimal

from pydantic import BaseModel

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema

_HEADER = "time|open|high|low|close|volume|quote_vol|trades|taker_buy_vol"
_HIGH_PRICE_THRESHOLD = 1000
_MID_PRICE_THRESHOLD = 1


def dump_json(model: BaseModel) -> str:
    return model.model_dump_json()


def dump_optional_json(model: BaseModel | None) -> str | None:
    if model is None:
        return None
    return model.model_dump_json()


def _fmt_decimal(value: Decimal | None, precision: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{precision}f}"


def format_indicators_compact(indicators: TechnicalIndicatorsSchema) -> str:
    """One-line key=value format for LLM consumption (~80 tokens vs ~600)."""
    parts: list[str] = []
    parts.append(f"RSI={_fmt_decimal(indicators.rsi_14, 1)}")
    parts.append(f"EMA20={_fmt_decimal(indicators.ema_20)}")
    parts.append(f"EMA50={_fmt_decimal(indicators.ema_50)}")
    parts.append(f"EMA200={_fmt_decimal(indicators.ema_200)}")
    parts.append(f"SMA20={_fmt_decimal(indicators.sma_20)}")
    parts.append(f"ATR={_fmt_decimal(indicators.atr_14)}")
    if indicators.macd is not None:
        m = indicators.macd
        parts.append(
            f"MACD={_fmt_decimal(m.macd_line)}"
            f"/{_fmt_decimal(m.signal_line)}"
            f"/{_fmt_decimal(m.histogram)}"
        )
    if indicators.bollinger is not None:
        b = indicators.bollinger
        parts.append(
            f"BB={_fmt_decimal(b.upper)}/{_fmt_decimal(b.lower)}"
            f"/%B={_fmt_decimal(b.percent_b)}/w={_fmt_decimal(b.width, 1)}"
        )
    if indicators.volume is not None:
        parts.append(f"vol_ratio={_fmt_decimal(indicators.volume.volume_ratio, 1)}")
    return " ".join(parts)


def format_order_flow_compact(
    order_flow: OrderFlowSchema | None,
) -> str | None:
    """One-line key=value format for order flow (~50 tokens vs ~400)."""
    if order_flow is None:
        return None
    of = order_flow
    div = of.oi_funding_divergence_direction or "none"
    return (
        f"funding={float(of.funding_rate):.4f}"
        f" zscore={_fmt_decimal(of.funding_zscore, 1)}"
        f" OI={float(of.open_interest):.0f}"
        f" OI_1h={float(of.oi_change_1h_percent):+.1f}%"
        f" OI_24h={float(of.oi_change_24h_percent):+.1f}%"
        f" L/S={_fmt_decimal(of.long_short_ratio, 2)}"
        f" L%={_fmt_decimal(of.long_account_percent, 1)}"
        f" S%={_fmt_decimal(of.short_account_percent, 1)}"
        f" div={div}"
    )


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
