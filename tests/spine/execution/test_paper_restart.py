from decimal import Decimal

import pytest

from kavzi_trader.paper.state_initializer import PaperStateInitializer
from tests.spine.execution.rebalance_rig import SYMBOL, Rig, make_intent

START_BALANCE = Decimal(1000)


async def _restart(old: Rig, reset_on_start: bool, balance: Decimal) -> Rig:
    """A fresh exchange and state manager over the old rig's Redis."""
    new = Rig()
    new.redis = old.redis
    new.price = old.price
    new.state._redis_client._client = old.redis  # type: ignore[assignment]
    await PaperStateInitializer().initialize(
        new.exchange,
        new.state,
        balance_usdt=balance,
        reset_on_start=reset_on_start,
    )
    return new


@pytest.fixture
async def opened() -> Rig:
    rig = Rig()
    await PaperStateInitializer().initialize(
        rig.exchange, rig.state, balance_usdt=START_BALANCE, reset_on_start=True
    )
    await rig.deliver(make_intent("i1", "0.3").model_dump_json())
    return rig


async def test_restart_restores_exchange_and_reconciles_clean(opened: Rig) -> None:
    before = await opened.position()
    assert before is not None
    stop_ids = {o.order_id for o in await opened.exchange.get_open_orders(SYMBOL)}

    restarted = await _restart(opened, False, Decimal(5))

    assert restarted.exchange.balance_usdt == Decimal(700)
    assert await restarted.stop_orders() == [(Decimal(3), Decimal(70))]
    restored_ids = {o.order_id for o in await restarted.exchange.get_open_orders()}
    assert restored_ids == stop_ids
    info = await restarted.exchange.get_account_info()
    assert Decimal(info["totalInitialMargin"]) == Decimal(300)
    assert await restarted.position() == before

    result = await restarted.state.reconcile_with_exchange()
    assert result.success
    assert result.discrepancies == []

    # shrink uses the restored stop id for cancel and replace, then close frees margin
    await restarted.deliver(make_intent("i2", "0.1").model_dump_json())
    shrunk = await restarted.position()
    assert shrunk is not None
    assert shrunk.quantity == Decimal(1)
    assert await restarted.stop_orders() == [(Decimal(1), Decimal(70))]
    shrunk_info = await restarted.exchange.get_account_info()
    assert Decimal(shrunk_info["totalInitialMargin"]) == Decimal(100)

    await restarted.deliver(make_intent("i3", "0").model_dump_json())
    assert await restarted.position() is None
    assert await restarted.stop_orders() == []
    info = await restarted.exchange.get_account_info()
    assert Decimal(info["totalInitialMargin"]) == Decimal(0)
    assert Decimal(info["availableBalance"]) == Decimal(1000)


async def test_restart_with_reset_wipes_redis(opened: Rig) -> None:
    restarted = await _restart(opened, True, Decimal(500))

    assert await restarted.position() is None
    assert await restarted.state.get_open_orders() == []
    account = await restarted.state.get_account_state()
    assert account is not None
    assert account.total_balance_usdt == Decimal(500)


async def test_first_run_without_reset_creates_fresh_account() -> None:
    rig = Rig()
    restarted = await _restart(rig, False, Decimal(750))

    account = await restarted.state.get_account_state()
    assert account is not None
    assert account.total_balance_usdt == Decimal(750)
    assert await restarted.state.get_all_positions() == []
