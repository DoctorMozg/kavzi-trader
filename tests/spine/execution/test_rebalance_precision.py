from decimal import Decimal

import pytest

from tests.spine.execution.rebalance_rig import Rig, make_intent
from tests.spine.precision.filters import make_precision


@pytest.fixture
async def rig() -> Rig:
    rig = Rig(precision=make_precision())
    await rig.state.reset_for_paper(Decimal(1000))
    return rig


async def test_target_quantity_is_floored_to_exchange_step(rig: Rig) -> None:
    # 0.4333 * 1000 / 100 = 4.333... units, step is 0.01
    await rig.deliver(make_intent("i1", "0.4333").model_dump_json())

    pos = await rig.position()
    assert pos is not None
    assert pos.quantity == Decimal("4.33")


async def test_disaster_stop_is_tick_aligned_toward_entry(rig: Rig) -> None:
    rig.price = Decimal("100.3")
    await rig.deliver(make_intent("i1", "0.3").model_dump_json())

    pos = await rig.position()
    assert pos is not None
    # entry 100.3 * 0.7 = 70.21; long stop rounds up to the 0.5 tick
    assert pos.stop_loss == Decimal("70.5")


async def test_resize_below_exchange_min_notional_sends_no_order(rig: Rig) -> None:
    await rig.deliver(make_intent("i1", "0.3").model_dump_json())
    # +0.5 units at 100 is a 50 USDT order, over the config floor but under 100
    result = await rig.engine.rebalance.execute(make_intent("i2", "0.35"))

    assert result.status == "REJECTED"
    assert "order_not_tradable" in (result.error_message or "")
    pos = await rig.position()
    assert pos is not None
    assert pos.quantity == Decimal(3)
