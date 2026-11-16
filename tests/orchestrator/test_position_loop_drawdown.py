from decimal import Decimal
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.position_action_type import PositionActionType
from kavzi_trader.domain.state_schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.orchestrator.loops.position import PositionManagementLoop
from kavzi_trader.spine.risk.drawdown_circuit_breaker import DrawdownCircuitBreaker

CLOSE_ALL_PERCENT = Decimal(10)


def _position(
    pos_id: str,
    symbol: str,
    exit_policy: Literal["BRACKET", "SIGNAL"],
) -> PositionSchema:
    now = utc_now()
    return PositionSchema(
        id=pos_id,
        symbol=symbol,
        side="LONG",
        quantity=Decimal(1),
        entry_price=Decimal(100),
        stop_loss=Decimal(90),
        take_profit=Decimal(120) if exit_policy == "BRACKET" else None,
        current_stop_loss=Decimal(90),
        management_config=PositionManagementConfigSchema(),
        exit_policy=exit_policy,
        opened_at=now,
        updated_at=now,
    )


class FakeBook:
    """Open positions that disappear once the executor closes them."""

    def __init__(self, positions: list[PositionSchema]) -> None:
        self.positions = positions
        self.drawdown = Decimal(0)
        self.state = MagicMock()
        self.state.get_all_positions = AsyncMock(
            side_effect=lambda: list(self.positions)
        )
        self.state.get_current_drawdown = AsyncMock(side_effect=lambda: self.drawdown)
        self.executor = AsyncMock()
        self.executor.execute = AsyncMock(side_effect=self._close)

    async def _close(self, position: PositionSchema, action: object) -> Decimal:
        self.positions = [p for p in self.positions if p.id != position.id]
        return Decimal(95)


@pytest.fixture
def book() -> FakeBook:
    return FakeBook(
        [
            _position("p1", "BTCUSDT", "BRACKET"),
            _position("p2", "ETHUSDT", "SIGNAL"),
        ]
    )


@pytest.fixture
def events() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def loop(book: FakeBook, events: AsyncMock) -> PositionManagementLoop:
    manager = AsyncMock()
    manager.evaluate_position = AsyncMock(return_value=[])
    return PositionManagementLoop(
        manager=manager,
        state_manager=book.state,
        atr_provider=AsyncMock(get_atr=AsyncMock(return_value=Decimal(5))),
        price_provider=AsyncMock(
            get_current_price=AsyncMock(return_value=Decimal(100)),
        ),
        action_executor=book.executor,
        fill_detector=AsyncMock(detect=AsyncMock(return_value=None)),
        interval_s=5,
        drawdown_breaker=DrawdownCircuitBreaker(
            CLOSE_ALL_PERCENT,
            book.state,
            events,
        ),
    )


async def test_drawdown_past_threshold_closes_every_position_once(
    loop: PositionManagementLoop, book: FakeBook, events: AsyncMock
) -> None:
    book.drawdown = Decimal(10)

    await loop._manage_positions()

    closed = {c.args[0].id: c.args[1] for c in book.executor.execute.await_args_list}
    assert set(closed) == {"p1", "p2"}  # BRACKET and SIGNAL alike
    assert all(a.action == PositionActionType.FULL_EXIT for a in closed.values())
    assert book.positions == []
    events.record.assert_awaited_once()


async def test_second_tick_does_not_close_again(
    loop: PositionManagementLoop, book: FakeBook, events: AsyncMock
) -> None:
    book.drawdown = Decimal(12)

    await loop._manage_positions()
    await loop._manage_positions()

    assert book.executor.execute.await_count == 2
    events.record.assert_awaited_once()


async def test_failed_close_is_retried_next_tick(
    loop: PositionManagementLoop, book: FakeBook
) -> None:
    book.drawdown = Decimal(12)
    failures = {"p1": 1}

    async def flaky_close(position: PositionSchema, action: object) -> Decimal:
        if failures.get(position.id):
            failures[position.id] -= 1
            raise RuntimeError("exchange down")
        return await book._close(position, action)

    book.executor.execute.side_effect = flaky_close

    await loop._manage_positions()  # p1 fails, p2 still closes
    assert [p.id for p in book.positions] == ["p1"]

    await loop._manage_positions()

    assert book.positions == []


async def test_below_threshold_leaves_positions_alone(
    loop: PositionManagementLoop, book: FakeBook, events: AsyncMock
) -> None:
    book.drawdown = Decimal("9.9")

    await loop._manage_positions()

    book.executor.execute.assert_not_awaited()
    assert len(book.positions) == 2
    events.record.assert_not_awaited()
