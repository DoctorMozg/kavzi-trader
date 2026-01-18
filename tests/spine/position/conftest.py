from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest

from kavzi_trader.spine.state.schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)


@pytest.fixture()
def position_factory() -> Callable[..., PositionSchema]:
    def _factory(
        side: Literal["LONG", "SHORT"] = "LONG",
        entry_price: Decimal = Decimal("100"),
        quantity: Decimal = Decimal("1"),
        current_stop_loss: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        stop_loss_moved_to_breakeven: bool = False,
        partial_exit_done: bool = False,
        opened_at: datetime | None = None,
        updated_at: datetime | None = None,
        management_config: PositionManagementConfigSchema | None = None,
    ) -> PositionSchema:
        now = datetime.now(UTC)
        if opened_at is None:
            opened_at = now
        if updated_at is None:
            updated_at = now

        if stop_loss is None:
            stop_loss = Decimal("90") if side == "LONG" else Decimal("110")
        if take_profit is None:
            take_profit = Decimal("120") if side == "LONG" else Decimal("80")
        if current_stop_loss is None:
            current_stop_loss = stop_loss

        if management_config is None:
            management_config = PositionManagementConfigSchema()

        data = {
            "id": "pos-1",
            "symbol": "BTCUSDT",
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "current_stop_loss": current_stop_loss,
            "management_config": management_config,
            "stop_loss_moved_to_breakeven": stop_loss_moved_to_breakeven,
            "partial_exit_done": partial_exit_done,
            "opened_at": opened_at,
            "updated_at": updated_at,
        }
        return PositionSchema.model_validate(data)

    return _factory
