import logging
from decimal import Decimal

from pydantic import ValidationError

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.spine.state.redis_client import RedisStateClient
from kavzi_trader.spine.state.schemas import AccountStateSchema

logger = logging.getLogger(__name__)

ACCOUNT_KEY = "kt:state:account"


class AccountStore:
    def __init__(self, redis_client: RedisStateClient) -> None:
        self._redis = redis_client

    async def get(self) -> AccountStateSchema | None:
        data = await self._redis.get(ACCOUNT_KEY)
        if not data:
            return None
        try:
            return AccountStateSchema.model_validate_json(data)
        except ValidationError:
            logger.exception("Corrupt account state in Redis")
            return None

    async def save(self, account: AccountStateSchema) -> None:
        await self._redis.set(ACCOUNT_KEY, account.model_dump_json())
        logger.debug("Saved account state: balance=%s", account.total_balance_usdt)

    async def update_balance(
        self,
        total_balance: Decimal,
        available_balance: Decimal,
        locked_balance: Decimal,
        unrealized_pnl: Decimal = Decimal(0),
    ) -> AccountStateSchema:
        current = await self.get()

        peak_balance = total_balance
        if current and current.peak_balance > total_balance:
            peak_balance = current.peak_balance

        drawdown = Decimal(0)
        if peak_balance > 0:
            drawdown = ((peak_balance - total_balance) / peak_balance) * 100

        new_state = AccountStateSchema(
            total_balance_usdt=total_balance,
            available_balance_usdt=available_balance,
            locked_balance_usdt=locked_balance,
            unrealized_pnl=unrealized_pnl,
            peak_balance=peak_balance,
            current_drawdown_percent=drawdown,
            updated_at=utc_now(),
        )

        await self.save(new_state)
        return new_state

    async def get_drawdown(self) -> Decimal:
        account = await self.get()
        if not account:
            return Decimal(0)
        return account.current_drawdown_percent

    async def reset_peak_balance(self) -> None:
        account = await self.get()
        if account:
            new_state = AccountStateSchema(
                total_balance_usdt=account.total_balance_usdt,
                available_balance_usdt=account.available_balance_usdt,
                locked_balance_usdt=account.locked_balance_usdt,
                unrealized_pnl=account.unrealized_pnl,
                peak_balance=account.total_balance_usdt,
                current_drawdown_percent=Decimal(0),
                updated_at=utc_now(),
            )
            await self.save(new_state)
