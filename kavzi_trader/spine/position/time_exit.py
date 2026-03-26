import logging
from datetime import datetime

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class TimeExitChecker:
    """Flags positions that have been open longer than the allowed window."""

    def evaluate(self, position: PositionSchema) -> PositionActionSchema | None:
        now = utc_now()
        opened_at = self._normalize_time(position.opened_at, now)
        elapsed = now - opened_at
        max_seconds = position.management_config.max_hold_time_hours * 3600

        if elapsed.total_seconds() < max_seconds:
            return None

        logger.debug(
            "Time exit triggered for %s: elapsed=%ds max=%ds",
            position.symbol,
            int(elapsed.total_seconds()),
            max_seconds,
        )
        return PositionActionSchema(
            action=PositionActionType.FULL_EXIT,
            reason="time_exit",
        )

    def _normalize_time(self, opened_at: datetime, now: datetime) -> datetime:
        if opened_at.tzinfo is None and now.tzinfo is not None:
            return opened_at.replace(tzinfo=now.tzinfo)
        if opened_at.tzinfo is not None and now.tzinfo is None:
            return opened_at.replace(tzinfo=None)
        return opened_at
