from decimal import Decimal
from unittest.mock import patch

import pytest

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.order_enums import OrderType
from kavzi_trader.domain.state_schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)
from tests.spine.execution.rebalance_rig import (
    INTENT_TTL_MS,
    SIM_START_MS,
    SYMBOL,
    Rig,
    make_intent,
)


@pytest.fixture
async def rig() -> Rig:
    rig = Rig()
    await rig.state.reset_for_paper(Decimal(1000))
    return rig


async def test_open_grow_shrink_close_round_trip(rig: Rig) -> None:
    # open: weight 0.3 of 1000 at 100 -> 3 units
    await rig.deliver(make_intent("i1", "0.3").model_dump_json())
    pos = await rig.position()
    assert pos is not None
    assert (pos.quantity, pos.entry_price) == (Decimal(3), Decimal(100))
    assert (pos.strategy, pos.exit_policy, pos.take_profit) == ("trend", "SIGNAL", None)
    assert pos.stop_loss == Decimal(70)
    assert await rig.stop_orders() == [(Decimal(3), Decimal(70))]
    position_id = pos.id

    # grow at 110; equity is still 1000, synced at the 100 open with no unrealised pnl
    rig.price = Decimal(110)
    await rig.deliver(make_intent("i2", "0.5").model_dump_json())
    pos = await rig.position()
    assert pos is not None
    grown_qty = Decimal("0.5") * Decimal(1000) / Decimal(110)
    grown_qty = grown_qty.quantize(Decimal("0.00000001"), rounding="ROUND_DOWN")
    assert pos.id == position_id
    assert pos.quantity == grown_qty
    assert pos.entry_price == (
        (Decimal(100) * 3 + Decimal(110) * (grown_qty - 3)) / grown_qty
    )
    assert await rig.stop_orders() == [(grown_qty, pos.stop_loss)]

    # shrink at 110 to 0.1 weight of equity that now includes unrealised pnl
    await rig.deliver(make_intent("i3", "0.1").model_dump_json())
    shrunk = await rig.position()
    assert shrunk is not None
    equity = Decimal(1000) + (Decimal(110) - pos.entry_price) * grown_qty
    shrunk_qty = (Decimal("0.1") * equity / Decimal(110)).quantize(
        Decimal("0.00000001"), rounding="ROUND_DOWN"
    )
    assert shrunk.id == position_id
    assert shrunk.quantity == shrunk_qty
    assert shrunk.entry_price == pos.entry_price
    assert await rig.stop_orders() == [(shrunk_qty, shrunk.stop_loss)]

    # close
    rig.price = Decimal(120)
    await rig.deliver(make_intent("i4", "0").model_dump_json())
    assert await rig.position() is None
    assert await rig.stop_orders() == []
    rig.close_recorder.record_position_close.assert_awaited_once()
    closed, reason, exit_price = (
        rig.close_recorder.record_position_close.await_args.args
    )
    assert (closed.id, reason, exit_price) == (position_id, "Strategy signal", 120)
    assert exit_price > closed.entry_price  # profitable round trip
    assert rig.redis.lists["kt:decisions:processing"] == []


async def test_same_intent_delivered_twice_places_one_order(rig: Rig) -> None:
    raw = make_intent("dup", "0.5").model_dump_json()
    with patch.object(
        rig.exchange, "create_order", wraps=rig.exchange.create_order
    ) as create:
        await rig.deliver(raw)
        market_calls = [
            c
            for c in create.call_args_list
            if c.kwargs["order_type"] == OrderType.MARKET
        ]
        assert len(market_calls) == 1
        await rig.deliver(raw)
        await rig.deliver(make_intent("other-id", "0.5").model_dump_json())
        market_calls = [
            c
            for c in create.call_args_list
            if c.kwargs["order_type"] == OrderType.MARKET
        ]
    assert len(market_calls) == 1
    pos = await rig.position()
    assert pos is not None
    assert pos.quantity == Decimal(5)


async def test_events_carry_strategy(rig: Rig) -> None:
    await rig.deliver(make_intent("ev", "0.5").model_dump_json())
    await rig.deliver(make_intent("ev2", "0").model_dump_json())
    recorded = {
        call.args[0].event_type: call.args[0].data
        for call in rig.events.append.await_args_list
    }
    assert recorded["position_opened"]["strategy"] == "trend"
    assert recorded["position_closed"]["strategy"] == "trend"
    assert recorded["order_created"]["strategy"] == "trend"


async def test_bracket_position_in_symbol_is_not_resized(rig: Rig) -> None:
    now = utc_now()
    bracket = PositionSchema(
        id="llm-1",
        symbol=SYMBOL,
        side="LONG",
        quantity=Decimal(1),
        entry_price=Decimal(100),
        stop_loss=Decimal(95),
        take_profit=Decimal(110),
        current_stop_loss=Decimal(95),
        management_config=PositionManagementConfigSchema(),
        opened_at=now,
        updated_at=now,
    )
    await rig.state.update_position(bracket)
    await rig.deliver(make_intent("blocked", "0.5").model_dump_json())
    pos = await rig.position()
    assert pos is not None
    assert pos.exit_policy == "BRACKET"
    assert pos.quantity == Decimal(1)


async def test_spine_reads_the_injected_clock(rig: Rig) -> None:
    await rig.deliver(make_intent("at-start", "0.3").model_dump_json())
    pos = await rig.position()
    assert pos is not None
    assert int(pos.opened_at.timestamp() * 1000) == SIM_START_MS

    # Past its expiry in sim time, though still years before the wall clock.
    rig.clock.advance_to(SIM_START_MS + INTENT_TTL_MS + 1)
    await rig.deliver(make_intent("late", "0.6").model_dump_json())
    pos = await rig.position()
    assert pos is not None
    assert pos.quantity == Decimal(3)
    rejected = [
        call.args[0]
        for call in rig.events.append.await_args_list
        if call.args[0].event_type == "order_rejected"
    ]
    assert [e.aggregate_id for e in rejected] == ["late"]
