import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from kavzi_trader.domain.order_enums import OrderSide
from kavzi_trader.domain.state_schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)


def _position(side: str) -> PositionSchema:
    now = datetime.now(UTC)
    return PositionSchema.model_validate(
        {
            "id": "p1",
            "symbol": "BTCUSDT",
            "side": side,
            "quantity": Decimal(1),
            "entry_price": Decimal(100),
            "stop_loss": Decimal(95),
            "take_profit": Decimal(110),
            "current_stop_loss": Decimal(95),
            "management_config": PositionManagementConfigSchema(),
            "opened_at": now,
            "updated_at": now,
        },
    )


@pytest.mark.parametrize(
    ("side", "expected"),
    [("LONG", OrderSide.SELL), ("SHORT", OrderSide.BUY)],
)
def test_exit_side_is_opposite_of_position_side(
    side: str,
    expected: OrderSide,
) -> None:
    assert _position(side).exit_side == expected


def test_exit_side_is_not_serialized() -> None:
    assert "exit_side" not in _position("LONG").model_dump()


def _payload() -> dict[str, object]:
    return _position("LONG").model_dump(
        exclude={"strategy", "exit_policy"}, mode="json"
    )


def test_legacy_payload_loads_as_bracket_llm_pipeline() -> None:
    legacy = PositionSchema.model_validate_json(json.dumps(_payload()))

    assert legacy.exit_policy == "BRACKET"
    assert legacy.strategy == "llm_pipeline"
    assert legacy.take_profit == Decimal(110)


def test_bracket_position_without_take_profit_is_rejected() -> None:
    payload = _payload() | {"take_profit": None}

    with pytest.raises(ValidationError, match="requires take_profit"):
        PositionSchema.model_validate(payload)


def test_signal_position_without_take_profit_is_accepted() -> None:
    payload = _payload() | {"take_profit": None, "exit_policy": "SIGNAL"}

    position = PositionSchema.model_validate(payload)

    assert position.take_profit is None
    assert position.exit_policy == "SIGNAL"
