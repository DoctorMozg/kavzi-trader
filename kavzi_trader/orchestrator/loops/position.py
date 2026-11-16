from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Protocol

from kavzi_trader.commons.clock import Clock
from kavzi_trader.commons.system_clock import SYSTEM_CLOCK
from kavzi_trader.domain.position_action import PositionActionSchema
from kavzi_trader.domain.position_action_type import PositionActionType
from kavzi_trader.domain.state_schemas import PositionSchema
from kavzi_trader.orchestrator.loops.position_close_reporter import (
    PositionCloseReporter,
)
from kavzi_trader.spine.position.action_executor import PositionActionExecutor
from kavzi_trader.spine.position.exchange_fill_detector import ExchangeFillDetector
from kavzi_trader.spine.position.manager import PositionManager
from kavzi_trader.spine.risk.drawdown_circuit_breaker import DrawdownCircuitBreaker
from kavzi_trader.spine.state.manager import StateManager
from kavzi_trader.ui.recorder import UiEventRecorder

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
        fill_detector: ExchangeFillDetector,
        interval_s: int,
        ui_recorder: UiEventRecorder | None = None,
        cycle_timeout_s: int = 30,
        fill_check_interval_s: int = 15,
        tp_retry_max_attempts: int = 3,
        drawdown_breaker: DrawdownCircuitBreaker | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._clock = clock
        self._drawdown_breaker = drawdown_breaker
        self._manager = manager
        self._state_manager = state_manager
        self._atr_provider = atr_provider
        self._price_provider = price_provider
        self._action_executor = action_executor
        self._fill_detector = fill_detector
        self._interval_s = interval_s
        self._ui_recorder = ui_recorder
        self._close_reporter = PositionCloseReporter(ui_recorder, "position")
        self._cycle_timeout_s = cycle_timeout_s
        self._fill_check_interval_s = fill_check_interval_s
        self._last_fill_check_s: float | None = None
        self._tp_retry_max_attempts = tp_retry_max_attempts
        self._tp_retry_attempts: dict[str, int] = {}

    async def run(self) -> None:
        logger.info(
            "PositionManagementLoop started, interval=%ds",
            self._interval_s,
        )
        while True:
            try:
                await self.step()
            except Exception:
                logger.exception(
                    "PositionManagementLoop encountered an error, continuing",
                    extra={
                        "loop": "position",
                        "interval_s": self._interval_s,
                    },
                )
            await asyncio.sleep(self._interval_s)

    async def step(self) -> None:
        """Run one management cycle over every open position."""
        positions = await self._state_manager.get_all_positions()
        # Book exchange-side SL/TP fills first: the stop that caused a drawdown
        # must not be re-sold by the close-all below.
        if self._fill_check_due():
            if positions:
                positions = await self._drop_exchange_closed(positions)
            await self._sweep_orphaned_orders()
        if self._drawdown_breaker is not None and await self._drawdown_breaker.check(
            len(positions),
        ):
            await self._close_all(positions)
            return
        open_ids = {p.id for p in positions}
        self._tp_retry_attempts = {
            pid: n for pid, n in self._tp_retry_attempts.items() if pid in open_ids
        }
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

    async def _close_all(self, positions: list[PositionSchema]) -> None:
        """Full-exit every position; each failure is isolated and retried next tick."""
        action = PositionActionSchema(
            action=PositionActionType.FULL_EXIT,
            reason="Drawdown circuit breaker",
        )
        for position in positions:
            try:
                await self._apply_action(position, action)
            except Exception:
                logger.exception(
                    "Drawdown close-all failed for %s",
                    position.symbol,
                    extra={"loop": "position", "position_id": position.id},
                )

    async def _sweep_orphaned_orders(self) -> None:
        try:
            await self._action_executor.sweep_orphaned_orders()
        except Exception:
            logger.exception(
                "Orphaned order sweep failed",
                extra={"loop": "position"},
            )

    def _fill_check_due(self) -> bool:
        now_s = self._clock.now_ms() / 1000
        if (
            self._last_fill_check_s is not None
            and now_s - self._last_fill_check_s < self._fill_check_interval_s
        ):
            return False
        self._last_fill_check_s = now_s
        return True

    async def _drop_exchange_closed(
        self,
        positions: list[PositionSchema],
    ) -> list[PositionSchema]:
        """Handle positions the exchange closed via SL/TP; return the rest."""
        results = await asyncio.gather(
            *(self._handle_exchange_close(p) for p in positions),
        )
        return [p for p, closed in zip(positions, results, strict=True) if not closed]

    async def _handle_exchange_close(self, position: PositionSchema) -> bool:
        try:
            return await self._close_if_exchange_closed(position)
        except Exception:
            logger.exception(
                "Exchange fill check failed for %s",
                position.symbol,
                extra={"loop": "position", "position_id": position.id},
            )
            return False

    async def _close_if_exchange_closed(self, position: PositionSchema) -> bool:
        close = await self._fill_detector.detect(position)
        if close is None:
            return False
        exit_price = close.exit_price
        if exit_price is None:
            exit_price = await self._price_provider.get_current_price(position.symbol)
        logger.warning(
            "Position %s on %s was closed by the exchange (%s) at %s",
            position.id,
            position.symbol,
            close.close_reason,
            exit_price,
            extra={
                "loop": "position",
                "position_id": position.id,
                "symbol": position.symbol,
                "close_reason": close.close_reason,
                "exit_price": str(exit_price),
            },
        )
        await self._action_executor.close_after_exchange_fill(position)
        await self._close_reporter.report(
            position,
            close.close_reason,
            exit_price,
        )
        return True

    async def _manage_single_position(
        self,
        position: PositionSchema,
    ) -> None:
        try:
            if position.needs_tp_retry:
                position = await self._retry_take_profit(position)
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

    async def _retry_take_profit(self, position: PositionSchema) -> PositionSchema:
        """Re-place a missing TP a bounded number of times; return the latest state."""
        attempts = self._tp_retry_attempts.get(position.id, 0)
        if attempts >= self._tp_retry_max_attempts:
            return position
        try:
            await self._action_executor.retry_missing_take_profit(position)
        except Exception:
            attempts += 1
            self._tp_retry_attempts[position.id] = attempts
            extra = {
                "loop": "position",
                "position_id": position.id,
                "symbol": position.symbol,
            }
            if attempts >= self._tp_retry_max_attempts:
                logger.critical(
                    "Take-profit retries exhausted for %s; position is SL-only",
                    position.symbol,
                    extra=extra,
                    exc_info=True,
                )
            else:
                logger.exception(
                    "Take-profit retry %d/%d failed for %s",
                    attempts,
                    self._tp_retry_max_attempts,
                    position.symbol,
                    extra=extra,
                )
            return position
        self._tp_retry_attempts.pop(position.id, None)
        cleared = position.model_copy(
            update={"needs_tp_retry": False, "updated_at": self._clock.now()},
        )
        await self._state_manager.update_position(cleared)
        return cleared

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
        await self._safe_report_action(position, action)
        if action.action == PositionActionType.FULL_EXIT and exit_price is not None:
            await self._close_reporter.report(
                position,
                action.reason,
                exit_price,
            )

    async def _safe_report_action(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> None:
        if self._ui_recorder is None:
            return
        try:
            await self._ui_recorder.record_position_action(position, action)
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
