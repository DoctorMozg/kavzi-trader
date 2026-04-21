from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Literal, Protocol

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator
from kavzi_trader.spine.position.action_executor import PositionActionExecutor
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.spine.state.schemas import PositionSchema

logger = logging.getLogger(__name__)


class AtrProvider(Protocol):
    async def get_atr(self, symbol: str) -> Decimal: ...


class PriceProvider(Protocol):
    async def get_current_price(self, symbol: str) -> Decimal: ...


class PositionManagementLoop:
    """Applies position management actions at a fixed interval."""

    def __init__(
        self,
        manager: PositionManager,
        state_manager: StateManager,
        atr_provider: AtrProvider,
        price_provider: PriceProvider,
        action_executor: PositionActionExecutor,
        interval_s: int,
        report_populator: TradeReportPopulator | None = None,
        cycle_timeout_s: int = 30,
    ) -> None:
        self._manager = manager
        self._state_manager = state_manager
        self._atr_provider = atr_provider
        self._price_provider = price_provider
        self._action_executor = action_executor
        self._interval_s = interval_s
        self._report_populator = report_populator
        self._cycle_timeout_s = cycle_timeout_s

    async def run(self) -> None:
        logger.info(
            "PositionManagementLoop started, interval=%ds",
            self._interval_s,
        )
        while True:
            try:
                await self._manage_positions()
            except Exception:
                logger.exception(
                    "PositionManagementLoop encountered an error, continuing",
                    extra={
                        "loop": "position",
                        "interval_s": self._interval_s,
                    },
                )
            await asyncio.sleep(self._interval_s)

    async def _manage_positions(self) -> None:
        positions = await self._state_manager.get_all_positions()
        if positions:
            logger.debug(
                "Position management cycle: %d open positions",
                len(positions),
            )
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(self._manage_single_position(p) for p in positions),
                    return_exceptions=True,
                ),
                timeout=self._cycle_timeout_s,
            )
        except TimeoutError:
            logger.exception(
                "Position management cycle exceeded timeout, skipping",
                extra={
                    "loop": "position",
                    "cycle_timeout_s": self._cycle_timeout_s,
                    "position_count": len(positions),
                },
            )

    async def _manage_single_position(
        self,
        position: PositionSchema,
    ) -> None:
        try:
            current_price = await self._price_provider.get_current_price(
                position.symbol,
            )
            current_atr = await self._atr_provider.get_atr(position.symbol)
            if current_price <= 0:
                logger.warning(
                    "Skipping position management for %s: invalid price %s",
                    position.symbol,
                    current_price,
                )
                return
            if current_atr <= 0:
                logger.warning(
                    "Skipping position management for %s: invalid ATR %s",
                    position.symbol,
                    current_atr,
                )
                return
            actions = await self._manager.evaluate_position(
                position=position,
                current_price=current_price,
                current_atr=current_atr,
            )
            for action in actions:
                await self._apply_action(position, action)
                if action.action == PositionActionType.FULL_EXIT:
                    return
                try:
                    refreshed = await self._state_manager.get_position(
                        position.symbol,
                    )
                except Exception:
                    logger.exception(
                        "Failed to refresh position after action, "
                        "skipping remaining actions",
                        extra={
                            "loop": "position",
                            "position_id": position.id,
                            "symbol": position.symbol,
                        },
                    )
                    return
                if refreshed is None:
                    return
                position = refreshed
        except Exception:
            logger.exception(
                "Failed to manage position %s for %s",
                position.id,
                position.symbol,
                extra={
                    "loop": "position",
                    "position_id": position.id,
                    "symbol": position.symbol,
                },
            )

    async def _apply_action(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> None:
        if action.action == PositionActionType.NO_ACTION:
            return
        logger.info(
            "Position action: %s on %s — %s",
            action.action.value,
            position.symbol,
            action.reason,
            extra={
                "symbol": position.symbol,
                "position_id": position.id,
                "action": action.action.value,
            },
        )
        exit_price = await self._action_executor.execute(position, action)
        updated = self._build_updated_position(position, action)
        if updated is not None:
            await self._state_manager.update_position(updated)
        await self._safe_report_action(position, action)
        if action.action == PositionActionType.FULL_EXIT and exit_price is not None:
            await self._safe_report_position_close(
                position,
                action.reason,
                exit_price,
            )

    def _build_updated_position(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> PositionSchema | None:
        if action.action == PositionActionType.FULL_EXIT:
            return None
        if action.action == PositionActionType.MOVE_STOP_LOSS and action.new_stop_loss:
            update: dict[str, object] = {
                "current_stop_loss": action.new_stop_loss,
                "updated_at": utc_now(),
            }
            if action.reason == "break_even":
                update["stop_loss_moved_to_breakeven"] = True
            return position.model_copy(update=update)
        if action.action == PositionActionType.PARTIAL_EXIT and action.exit_quantity:
            return position.model_copy(
                update={
                    "quantity": position.quantity - action.exit_quantity,
                    "partial_exit_done": True,
                    "updated_at": utc_now(),
                },
            )
        return None

    async def _safe_report_action(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> None:
        if self._report_populator is None:
            return
        try:
            await self._report_populator.record_action(
                action_type=action.action.value.lower(),
                symbol=position.symbol,
                summary=action.reason,
            )
        except Exception:
            logger.exception(
                "Failed to report action %s for %s",
                action.action.value,
                position.symbol,
                extra={
                    "loop": "position",
                    "position_id": position.id,
                    "symbol": position.symbol,
                    "action": action.action.value,
                },
            )

    async def _safe_report_position_close(
        self,
        position: PositionSchema,
        close_reason: str,
        exit_price: Decimal,
    ) -> None:
        if self._report_populator is None:
            return
        try:
            side: Literal["LONG", "SHORT"] = position.side  # type: ignore[assignment]
            await self._report_populator.record_position_close(
                symbol=position.symbol,
                side=side,
                quantity=position.quantity,
                entry_price=position.entry_price,
                exit_price=exit_price,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                close_reason=close_reason,
                leverage=position.leverage,
                opened_at=position.opened_at,
            )
        except Exception:
            logger.exception(
                "Failed to report position close for %s",
                position.symbol,
                extra={
                    "loop": "position",
                    "position_id": position.id,
                    "symbol": position.symbol,
                    "close_reason": close_reason,
                },
            )
