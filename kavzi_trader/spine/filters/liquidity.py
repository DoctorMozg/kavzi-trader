import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.filter_result_schema import FilterResultSchema
from kavzi_trader.spine.filters.liquidity_period import LiquidityPeriod
from kavzi_trader.spine.filters.liquidity_session_schema import LiquiditySessionSchema

logger = logging.getLogger(__name__)

SATURDAY = 5
SUNDAY = 6
SUNDAY_REOPEN_HOUR = 20


class LiquidityFilter:
    """Adjusts position size based on expected market liquidity by time."""

    def __init__(
        self,
        config: FilterConfigSchema,
        time_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self._config = config
        self._time_provider = time_provider

    def evaluate(self, current_time: datetime | None = None) -> FilterResultSchema:
        now = current_time or self._time_provider()
        weekday = now.weekday()
        hour = now.hour

        if weekday == SATURDAY:
            return FilterResultSchema(
                name="liquidity",
                is_allowed=True,
                reason="weekend",
                size_multiplier=self._config.weekend_size_multiplier,
                period=LiquidityPeriod.LOW,
            )

        if weekday == SUNDAY and hour < SUNDAY_REOPEN_HOUR:
            return FilterResultSchema(
                name="liquidity",
                is_allowed=True,
                reason="weekend",
                size_multiplier=self._config.weekend_size_multiplier,
                period=LiquidityPeriod.LOW,
            )

        if weekday == SUNDAY and hour >= SUNDAY_REOPEN_HOUR:
            return FilterResultSchema(
                name="liquidity",
                is_allowed=True,
                reason="sunday_reopen",
                size_multiplier=self._config.sunday_after_20utc_multiplier,
                period=LiquidityPeriod.MEDIUM,
            )

        session = self._find_session(hour, self._config.liquidity_sessions)
        period = session.period if session else LiquidityPeriod.LOW
        multiplier = self._session_multiplier(
            period,
            self._config.liquidity_multipliers,
        )

        logger.debug(
            "Liquidity filter: day=%d hour=%d period=%s multiplier=%s",
            weekday, hour, period.value, multiplier,
        )
        return FilterResultSchema(
            name="liquidity",
            is_allowed=True,
            reason=None,
            size_multiplier=multiplier,
            period=period,
        )

    def _find_session(
        self,
        hour: int,
        sessions: list[LiquiditySessionSchema],
    ) -> LiquiditySessionSchema | None:
        for session in sessions:
            if self._in_session(hour, session.start_hour, session.end_hour):
                return session
        return None

    def _in_session(self, hour: int, start: int, end: int) -> bool:
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end

    def _session_multiplier(
        self,
        period: LiquidityPeriod,
        multipliers: dict[str, Decimal],
    ) -> Decimal:
        return multipliers.get(period.value, Decimal("1.0"))
