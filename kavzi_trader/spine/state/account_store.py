import asyncio
import logging
import math
from decimal import Decimal

from pydantic import ValidationError

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.state_schemas import AccountStateSchema
from kavzi_trader.infra.redis_client import RedisStateClient

logger = logging.getLogger(__name__)

ACCOUNT_KEY = "kt:state:account"

# Fraction of the peak balance retained per elapsed day. ~2%/day decay lets
# drawdown recover automatically when the balance stays flat below the peak,
# so a >=5% DD with no open positions does not pause the system forever.
PEAK_DECAY_PER_DAY = 0.98
SECONDS_PER_DAY = 86400


class AccountStore:
    def __init__(self, redis_client: RedisStateClient) -> None:
        self._redis = redis_client
        # Serializes read-compute-write sequences against peak_balance so
        # concurrent reconciler + user-data stream updates cannot clobber
        # each other's peak/drawdown derivations.
        self._lock = asyncio.Lock()

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
        async with self._lock:
            current = await self.get()
            now = utc_now()

            # Decay the stored peak toward the current balance over elapsed
            # whole days so a stale peak cannot keep drawdown elevated
            # indefinitely. Whole-day granularity keeps frequent intra-day
            # balance updates from nudging the peak on sub-second jitter; with
            # no prior timestamp (legacy records / fresh state) elapsed is 0,
            # so the multiplier is 1.0 and the peak is left untouched.
            peak_balance = total_balance
            if current and current.peak_balance > total_balance:
                days_elapsed = 0
                if current.peak_balance_updated_at is not None:
                    elapsed_s = (now - current.peak_balance_updated_at).total_seconds()
                    days_elapsed = max(0, math.floor(elapsed_s / SECONDS_PER_DAY))

                decay_multiplier = Decimal(str(PEAK_DECAY_PER_DAY**days_elapsed))
                decayed_peak = current.peak_balance * decay_multiplier
                peak_balance = max(total_balance, decayed_peak)

            drawdown = Decimal(0)
            if peak_balance > 0:
                drawdown = ((peak_balance - total_balance) / peak_balance) * 100

            # Why: Binance's user-data balance payload does not surface a
            # wallet-level margin ratio directly; locked/total is the
            # simplest local proxy for "wallet fraction tied up in margin"
            # and is what the downstream guard threshold was designed against.
            margin_ratio = Decimal(0)
            if total_balance > 0:
                margin_ratio = locked_balance / total_balance

            total_margin_balance = total_balance + unrealized_pnl

            new_state = AccountStateSchema(
                total_balance_usdt=total_balance,
                available_balance_usdt=available_balance,
                locked_balance_usdt=locked_balance,
                unrealized_pnl=unrealized_pnl,
                peak_balance=peak_balance,
                peak_balance_updated_at=now,
                current_drawdown_percent=drawdown,
                total_margin_balance=total_margin_balance,
                margin_ratio=margin_ratio,
                updated_at=now,
            )

            await self.save(new_state)
            logger.debug(
                "Updated account: peak=%s margin_ratio=%s",
                peak_balance,
                margin_ratio,
            )
            return new_state

    async def get_drawdown(self) -> Decimal:
        account = await self.get()
        if not account:
            return Decimal(0)
        return account.current_drawdown_percent
