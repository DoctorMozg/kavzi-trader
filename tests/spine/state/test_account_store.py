import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from kavzi_trader.spine.state.account_store import AccountStore
from kavzi_trader.spine.state.schemas import AccountStateSchema


class TestAccountStore:
    @pytest.fixture
    def store(self, mock_redis_client: AsyncMock) -> AccountStore:
        store = AccountStore.__new__(AccountStore)
        store._redis = mock_redis_client
        store._lock = asyncio.Lock()
        return store

    async def test_save_account(
        self,
        store: AccountStore,
        sample_account_state: AccountStateSchema,
    ):
        await store.save(sample_account_state)

        store._redis.set.assert_called_once()

    async def test_get_account_found(
        self,
        store: AccountStore,
        sample_account_state: AccountStateSchema,
    ):
        store._redis.get.return_value = sample_account_state.model_dump_json()

        result = await store.get()

        assert result is not None
        assert result.total_balance_usdt == Decimal(10000)

    async def test_get_account_not_found(self, store: AccountStore):
        store._redis.get.return_value = None

        result = await store.get()

        assert result is None

    async def test_update_balance_new_account(self, store: AccountStore):
        store._redis.get.return_value = None

        result = await store.update_balance(
            total_balance=Decimal(10000),
            available_balance=Decimal(9000),
            locked_balance=Decimal(1000),
        )

        assert result.total_balance_usdt == Decimal(10000)
        assert result.peak_balance == Decimal(10000)
        assert result.current_drawdown_percent == Decimal(0)

    async def test_update_balance_tracks_peak(
        self,
        store: AccountStore,
        sample_account_state: AccountStateSchema,
    ):
        store._redis.get.return_value = sample_account_state.model_dump_json()

        result = await store.update_balance(
            total_balance=Decimal(9000),
            available_balance=Decimal(9000),
            locked_balance=Decimal(0),
        )

        assert result.peak_balance == Decimal(10500)
        assert result.current_drawdown_percent > Decimal(0)

    async def test_update_balance_new_peak(
        self,
        store: AccountStore,
        sample_account_state: AccountStateSchema,
    ):
        store._redis.get.return_value = sample_account_state.model_dump_json()

        result = await store.update_balance(
            total_balance=Decimal(11000),
            available_balance=Decimal(11000),
            locked_balance=Decimal(0),
        )

        assert result.peak_balance == Decimal(11000)
        assert result.current_drawdown_percent == Decimal(0)

    async def test_get_drawdown(
        self,
        store: AccountStore,
        sample_account_state: AccountStateSchema,
    ):
        store._redis.get.return_value = sample_account_state.model_dump_json()

        drawdown = await store.get_drawdown()

        assert drawdown == Decimal("4.76")

    async def test_get_drawdown_no_account(self, store: AccountStore):
        store._redis.get.return_value = None

        drawdown = await store.get_drawdown()

        assert drawdown == Decimal(0)

    async def test_reset_peak_balance(
        self,
        store: AccountStore,
        sample_account_state: AccountStateSchema,
    ):
        store._redis.get.return_value = sample_account_state.model_dump_json()

        await store.reset_peak_balance()

        store._redis.set.assert_called_once()

    async def test_update_balance_populates_margin_ratio(self, store: AccountStore):
        store._redis.get.return_value = None

        result = await store.update_balance(
            total_balance=Decimal(100),
            available_balance=Decimal(40),
            locked_balance=Decimal(60),
            unrealized_pnl=Decimal(0),
        )

        assert result.margin_ratio == Decimal("0.6")
        assert result.total_margin_balance == Decimal(100)

    async def test_update_balance_is_concurrency_safe(self, store: AccountStore):
        # Stateful in-memory Redis stub: concurrent update_balance calls must
        # serialize so the final peak_balance equals the maximum input total.
        state: dict[str, str | None] = {"payload": None}

        async def fake_get(_key: str) -> str | None:
            # Yield control to allow interleaving without the lock.
            await asyncio.sleep(0)
            return state["payload"]

        async def fake_set(_key: str, value: str) -> None:
            await asyncio.sleep(0)
            state["payload"] = value

        store._redis.get.side_effect = fake_get
        store._redis.set.side_effect = fake_set

        totals = [Decimal(100), Decimal(200), Decimal(300), Decimal(250)]
        await asyncio.gather(
            *(
                store.update_balance(
                    total_balance=total,
                    available_balance=total,
                    locked_balance=Decimal(0),
                )
                for total in totals
            )
        )

        final = await store.get()
        assert final is not None
        assert final.peak_balance == max(totals)
