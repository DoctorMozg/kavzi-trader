import logging
from decimal import Decimal

from kavzi_trader.order_flow.schemas import OIMomentumSchema, OpenInterestSchema

logger = logging.getLogger(__name__)

_MINUTES_IN_1H = 60
_MINUTES_IN_24H = 1440
# Binance openInterestHist periods usable for a 1h change (finest first).
_OI_PERIODS_MINUTES = (5, 15, 30)


def oi_period_minutes(interval_minutes: int) -> int:
    """Largest supported openInterestHist period not exceeding the interval."""
    if interval_minutes <= 0:
        msg = f"interval_minutes must be positive, got {interval_minutes}"
        raise ValueError(msg)
    fitting = [p for p in _OI_PERIODS_MINUTES if p <= interval_minutes]
    return fitting[-1] if fitting else _OI_PERIODS_MINUTES[0]


def periods_for_oi_period(period_minutes: int) -> tuple[int, int]:
    """Return (periods_1h, periods_24h) for an openInterestHist period."""
    return _MINUTES_IN_1H // period_minutes, _MINUTES_IN_24H // period_minutes


def calculate_oi_momentum(
    oi_history: list[OpenInterestSchema],
    periods_1h: int = 4,
    periods_24h: int = 96,
) -> OIMomentumSchema | None:
    if not oi_history:
        return None

    current_oi = oi_history[-1].open_interest

    oi_1h_ago = _get_oi_at_offset(oi_history, periods_1h)
    if oi_1h_ago is None:
        logger.warning(
            "OI history too short for 1h change: %d samples, need %d",
            len(oi_history),
            periods_1h + 1,
        )
        return None
    oi_24h_ago = _get_oi_at_offset(oi_history, periods_24h)
    if oi_24h_ago is None:
        logger.warning(
            "OI history too short for 24h change: %d samples, need %d",
            len(oi_history),
            periods_24h + 1,
        )

    return OIMomentumSchema(
        open_interest=current_oi,
        oi_change_1h_percent=_calculate_percent_change(current_oi, oi_1h_ago),
        oi_change_24h_percent=(
            None
            if oi_24h_ago is None
            else _calculate_percent_change(current_oi, oi_24h_ago)
        ),
    )


def _get_oi_at_offset(
    oi_history: list[OpenInterestSchema],
    offset: int,
) -> Decimal | None:
    if len(oi_history) <= offset:
        return None
    return oi_history[-(offset + 1)].open_interest


def _calculate_percent_change(current: Decimal, previous: Decimal) -> Decimal:
    if previous == 0:
        return Decimal(0)
    change = ((current - previous) / previous) * 100
    return change.quantize(Decimal("0.01"))
