from decimal import Decimal

from kavzi_trader.order_flow.schemas import OIMomentumSchema, OpenInterestSchema

_MINUTES_IN_1H = 60
_MINUTES_IN_24H = 1440


def periods_for_interval(interval_minutes: int) -> tuple[int, int]:
    """Return (periods_1h, periods_24h) for a given candle interval in minutes."""
    return _MINUTES_IN_1H // interval_minutes, _MINUTES_IN_24H // interval_minutes


def calculate_oi_momentum(
    oi_history: list[OpenInterestSchema],
    periods_1h: int = 4,
    periods_24h: int = 96,
) -> OIMomentumSchema | None:
    if not oi_history:
        return None

    current_oi = oi_history[-1].open_interest

    oi_1h_ago = _get_oi_at_offset(oi_history, periods_1h)
    oi_24h_ago = _get_oi_at_offset(oi_history, periods_24h)

    change_1h = _calculate_percent_change(current_oi, oi_1h_ago)
    change_24h = _calculate_percent_change(current_oi, oi_24h_ago)

    return OIMomentumSchema(
        open_interest=current_oi,
        oi_change_1h_percent=change_1h,
        oi_change_24h_percent=change_24h,
    )


def _get_oi_at_offset(
    oi_history: list[OpenInterestSchema],
    offset: int,
) -> Decimal:
    if not oi_history:
        return Decimal(0)
    if len(oi_history) <= offset:
        return oi_history[0].open_interest
    return oi_history[-(offset + 1)].open_interest


def _calculate_percent_change(current: Decimal, previous: Decimal) -> Decimal:
    if previous == 0:
        return Decimal(0)
    change = ((current - previous) / previous) * 100
    return change.quantize(Decimal("0.01"))
