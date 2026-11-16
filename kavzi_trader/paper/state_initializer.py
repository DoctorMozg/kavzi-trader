import logging
from decimal import Decimal

from kavzi_trader.paper.exchange import PaperExchangeClient
from kavzi_trader.spine.state.manager import StateManager

logger = logging.getLogger(__name__)


class PaperStateInitializer:
    """Brings Redis and the in-memory paper exchange to a consistent start state."""

    async def initialize(
        self,
        exchange: PaperExchangeClient,
        state_manager: StateManager,
        balance_usdt: Decimal,
        reset_on_start: bool,
    ) -> None:
        exchange.set_account_store(state_manager.account)
        if not reset_on_start:
            account = await state_manager.get_account_state()
            if account is not None:
                exchange.restore_from_state(
                    account,
                    await state_manager.get_all_positions(),
                    await state_manager.get_open_orders(),
                )
                return
            logger.info("No persisted paper account in Redis; starting fresh")
        await state_manager.reset_for_paper(balance_usdt)
        logger.info("Paper state reset in Redis: %s USDT", balance_usdt)
