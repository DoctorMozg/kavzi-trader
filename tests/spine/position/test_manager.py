from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kavzi_trader.domain.position_action_type import PositionActionType
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.position.partial_exit import PartialExitChecker
from kavzi_trader.spine.position.stall_exit import StallExitChecker
from kavzi_trader.spine.position.time_exit import TimeExitChecker


def build_manager(
    liquidation_emergency_percent: Decimal = Decimal("5.0"),
) -> PositionManager:
    return PositionManager(
        partial_exit=PartialExitChecker(),
        time_exit=TimeExitChecker(),
        stall_exit=StallExitChecker(),
        liquidation_emergency_percent=liquidation_emergency_percent,
    )


@pytest.mark.asyncio
async def test_manager_returns_time_exit_only(position_factory, monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    opened_at = now - timedelta(hours=30)
    position = position_factory(opened_at=opened_at, updated_at=opened_at)
    manager = build_manager()

    monkeypatch.setattr(
        "kavzi_trader.spine.position.time_exit.utc_now",
        lambda: now,
    )

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal(110),
        current_atr=Decimal(10),
    )

    assert actions is not None
    assert len(actions) == 1
    assert actions[0].reason == "time_exit"


@pytest.mark.asyncio
async def test_manager_includes_partial_exit(position_factory) -> None:
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    position = position_factory(
        entry_price=Decimal(100),
        take_profit=Decimal(120),
        opened_at=one_hour_ago,
        updated_at=one_hour_ago,
    )
    manager = build_manager()

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal(113),
        current_atr=Decimal(10),
    )

    assert any(action.reason == "partial_exit" for action in actions)


@pytest.mark.asyncio
async def test_stop_loss_breach_long_exits(position_factory) -> None:
    position = position_factory(
        side="LONG",
        entry_price=Decimal(100),
        current_stop_loss=Decimal(90),
    )
    manager = build_manager()

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal(89),
        current_atr=Decimal(10),
    )

    assert len(actions) == 1
    assert actions[0].action == PositionActionType.FULL_EXIT
    assert actions[0].reason == "Stop-loss breached"


@pytest.mark.asyncio
async def test_stop_loss_breach_short_exits(position_factory) -> None:
    position = position_factory(
        side="SHORT",
        entry_price=Decimal(100),
        current_stop_loss=Decimal(110),
    )
    manager = build_manager()

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal(111),
        current_atr=Decimal(10),
    )

    assert len(actions) == 1
    assert actions[0].action == PositionActionType.FULL_EXIT
    assert actions[0].reason == "Stop-loss breached"


@pytest.mark.asyncio
async def test_stop_loss_not_breached_continues(position_factory) -> None:
    position = position_factory(
        side="LONG",
        entry_price=Decimal(100),
        current_stop_loss=Decimal(90),
    )
    manager = build_manager()

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal(105),
        current_atr=Decimal(10),
    )

    assert not any(
        a.action == PositionActionType.FULL_EXIT and a.reason == "Stop-loss breached"
        for a in actions
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("emergency_percent", "expect_exit"),
    [(Decimal("5.0"), False), (Decimal("30.0"), True)],
)
async def test_manager_uses_configured_liquidation_emergency_percent(
    position_factory,
    emergency_percent: Decimal,
    expect_exit: bool,
) -> None:
    """Price 85 sits 25% of the entry-to-liquidation distance away from 80."""
    position = position_factory(stop_loss=Decimal(70)).model_copy(
        update={"liquidation_price": Decimal(80)},
    )
    manager = build_manager(emergency_percent)

    actions = await manager.evaluate_position(
        position=position,
        current_price=Decimal(85),
        current_atr=Decimal(1),
    )

    emergency = [a for a in actions or [] if "near liquidation" in a.reason]
    assert bool(emergency) is expect_exit
