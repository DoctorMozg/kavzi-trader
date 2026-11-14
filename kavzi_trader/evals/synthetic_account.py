from datetime import datetime
from decimal import Decimal

from kavzi_trader.domain.state_schemas import AccountStateSchema, PositionSchema


class SyntheticAccount:
    """Flat account with no positions, standing in for the Redis state store."""

    def __init__(self, balance_usdt: Decimal, as_of: datetime) -> None:
        self._state = AccountStateSchema(
            total_balance_usdt=balance_usdt,
            available_balance_usdt=balance_usdt,
            locked_balance_usdt=Decimal(0),
            peak_balance=balance_usdt,
            total_margin_balance=balance_usdt,
            updated_at=as_of,
        )

    async def get_account_state(self) -> AccountStateSchema | None:
        return self._state

    async def get_all_positions(self) -> list[PositionSchema]:
        return []
