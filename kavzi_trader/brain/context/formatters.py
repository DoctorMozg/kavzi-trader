from decimal import Decimal

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema

_HEADER = "time|open|high|low|close|volume"
_HIGH_PRICE_THRESHOLD = 1000
_MID_PRICE_THRESHOLD = 1


def _fmt_decimal(value: Decimal | None, precision: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{precision}f}"


def _price_based_precision(reference_price: Decimal) -> int:
    """Dynamic precision based on asset price magnitude.

    Prevents low-price assets (e.g. WIF at $0.18) from having their
    ATR/EMA/MACD values rounded to 0.00.
    """
    price = float(reference_price)
    if price >= _HIGH_PRICE_THRESHOLD:
        return 2
    if price >= _MID_PRICE_THRESHOLD:
        return 4
    return 6


def format_indicators_compact(
    indicators: TechnicalIndicatorsSchema,
    reference_price: Decimal | None = None,
) -> str:
    """One-line key=value format for LLM consumption (~80 tokens vs ~600)."""
    # Price-based precision for price-scale indicators (ATR, EMA, MACD, BB bands)
    pp = _price_based_precision(reference_price) if reference_price else 2

    parts: list[str] = []
    parts.append(f"RSI={_fmt_decimal(indicators.rsi_14, 1)}")
    parts.append(f"EMA20={_fmt_decimal(indicators.ema_20, pp)}")
    parts.append(f"EMA50={_fmt_decimal(indicators.ema_50, pp)}")
    parts.append(f"EMA200={_fmt_decimal(indicators.ema_200, pp)}")
    parts.append(f"SMA20={_fmt_decimal(indicators.sma_20, pp)}")
    parts.append(f"ATR={_fmt_decimal(indicators.atr_14, pp)}")
    if indicators.macd is not None:
        m = indicators.macd
        parts.append(
            f"MACD={_fmt_decimal(m.macd_line, pp)}"
            f"/{_fmt_decimal(m.signal_line, pp)}"
            f"/{_fmt_decimal(m.histogram, pp)}"
        )
    if indicators.bollinger is not None:
        b = indicators.bollinger
        parts.append(
            f"BB={_fmt_decimal(b.upper, pp)}/{_fmt_decimal(b.lower, pp)}"
            f"/%B={_fmt_decimal(b.percent_b)}/w={_fmt_decimal(b.width, 4)}"
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
        f" squeeze={of.squeeze_alert}"
        f" crowded_l={of.is_crowded_long}"
        f" crowded_s={of.is_crowded_short}"
    )


def _fmt_price(value: Decimal, precision: int) -> str:
    return f"{float(value):.{precision}f}"


def _detect_price_precision(candles: list[CandlestickSchema]) -> int:
    if not candles:
        return 2
    return _price_based_precision(candles[0].close_price)


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
        )
        rows.append(row)
    return "\n".join(rows)
