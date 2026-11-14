from decimal import Decimal
from typing import Protocol

from kavzi_trader.spine.state.schemas import PositionSchema


class PositionCloseRecorder(Protocol):
    """Observer for positions the engine closes itself, e.g. emergency closes."""

    async def record_position_close(
        self,
        position: PositionSchema,
        close_reason: str,
        exit_price: Decimal,
    ) -> None: ...
