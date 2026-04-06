import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import aiofiles
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel

from kavzi_trader.commons.path_utility import ensure_directory_exists
from kavzi_trader.commons.time_utility import timestamp_path, utc_now
from kavzi_trader.reporting.report_state_schema import (
    ReportActionEntrySchema,
    ReportClosedPositionEntrySchema,
    ReportMarketPriceSchema,
    ReportPositionEntrySchema,
    ReportStateSchema,
    ReportTradeEntrySchema,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class TradeReportPopulator:
    """Renders and updates a live HTML trade report using Jinja2."""

    def __init__(
        self,
        report_dir: Path,
        initial_balance_usdt: Decimal,
        max_action_entries: int = 500,
        max_trade_entries: int = 200,
        max_closed_position_entries: int = 100,
        refresh_interval_s: int = 3,
    ) -> None:
        ensure_directory_exists(report_dir)
        self._report_path = timestamp_path(
            "trade_report",
            report_dir,
            "html",
        )
        self._max_action_entries = max_action_entries
        self._max_trade_entries = max_trade_entries
        self._max_closed_position_entries = max_closed_position_entries
        self._refresh_interval_s = refresh_interval_s
        self._lock = asyncio.Lock()

        self._env = Environment(
            loader=FileSystemLoader(_TEMPLATES_DIR),
            undefined=StrictUndefined,
            autoescape=select_autoescape(("html", "htm", "xml")),
        )

        now = utc_now()
        self._state = ReportStateSchema(
            session_started_at=now,
            last_updated_at=now,
            version=1,
            initial_balance_usdt=initial_balance_usdt,
            current_balance_usdt=initial_balance_usdt,
            session_revenue_usdt=Decimal(0),
            unrealized_pnl_usdt=Decimal(0),
            active_positions_count=0,
            open_positions=[],
            closed_positions=[],
            market_prices=[],
            actions=[],
            trades=[],
        )
        logger.info("Report file: %s", self._report_path)

    @property
    def report_path(self) -> Path:
        return self._report_path

    @property
    def state(self) -> ReportStateSchema:
        return self._state

    async def _append_and_render(
        self,
        field: str,
        entry: BaseModel,
        max_entries: int,
    ) -> None:
        """Append an entry to a list field, trim to max, bump version, render."""
        async with self._lock:
            items = [*getattr(self._state, field), entry]
            if len(items) > max_entries:
                items = items[-max_entries:]
            self._state = self._state.model_copy(
                update={
                    field: items,
                    "last_updated_at": utc_now(),
                    "version": self._state.version + 1,
                },
            )
            await self._render()

    async def record_action(
        self,
        action_type: str,
        symbol: str,
        summary: str,
        details: str | None = None,
    ) -> None:
        """Add an entry to the general action log and re-render."""
        try:
            entry = ReportActionEntrySchema(
                timestamp=utc_now(),
                action_type=action_type,
                symbol=symbol,
                summary=summary,
                details=details,
            )
            await self._append_and_render(
                "actions",
                entry,
                self._max_action_entries,
            )
        except Exception:
            logger.exception(
                "Failed to record action %s for %s",
                action_type,
                symbol,
            )

    async def record_trade(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT", "CLOSE"],
        status: str,
        confidence: float,
        entry_price: Decimal | None = None,
        quantity: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        reasoning: str = "",
    ) -> None:
        """Add an entry to the buy/sell trade log and re-render."""
        try:
            entry = ReportTradeEntrySchema(
                timestamp=utc_now(),
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status=status,
                confidence=confidence,
                reasoning=reasoning,
            )
            await self._append_and_render(
                "trades",
                entry,
                self._max_trade_entries,
            )
        except Exception:
            logger.exception(
                "Failed to record trade %s for %s",
                side,
                symbol,
            )

    async def record_position_close(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        quantity: Decimal,
        entry_price: Decimal,
        exit_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        close_reason: str,
        leverage: int,
        opened_at: datetime,
    ) -> None:
        """Record a closed position with realized PnL and re-render."""
        try:
            if side == "LONG":
                pnl = (exit_price - entry_price) * quantity
            else:
                pnl = (entry_price - exit_price) * quantity
            entry = ReportClosedPositionEntrySchema(
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                exit_price=exit_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                pnl=pnl,
                close_reason=close_reason,
                leverage=leverage,
                opened_at=opened_at,
                closed_at=utc_now(),
            )
            await self._append_and_render(
                "closed_positions",
                entry,
                self._max_closed_position_entries,
            )
        except Exception:
            logger.exception(
                "Failed to record position close for %s",
                symbol,
            )

    async def update_balance(
        self,
        current_balance_usdt: Decimal,
        unrealized_pnl_usdt: Decimal = Decimal(0),
        active_positions_count: int = 0,
        open_positions: list[ReportPositionEntrySchema] | None = None,
        market_prices: list[ReportMarketPriceSchema] | None = None,
    ) -> None:
        """Update balance/revenue header, positions, prices and re-render."""
        try:
            revenue = current_balance_usdt - self._state.initial_balance_usdt
            update: dict[str, object] = {
                "current_balance_usdt": current_balance_usdt,
                "session_revenue_usdt": revenue,
                "unrealized_pnl_usdt": unrealized_pnl_usdt,
                "active_positions_count": active_positions_count,
                "last_updated_at": utc_now(),
                "version": self._state.version + 1,
            }
            if open_positions is not None:
                update["open_positions"] = open_positions
            if market_prices is not None:
                update["market_prices"] = market_prices
            async with self._lock:
                self._state = self._state.model_copy(update=update)
                await self._render()
        except Exception:
            logger.exception("Failed to update balance in report")

    async def _render(self) -> None:
        """Render current state to HTML and write atomically."""
        try:
            template = self._env.get_template("trade_report.html.j2")
            html = template.render(
                state=self._state,
                refresh_interval_s=self._refresh_interval_s,
            )
            tmp_path = self._report_path.with_suffix(".html.tmp")
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as fh:
                await fh.write(html)
            tmp_path.rename(self._report_path)
        except Exception:
            logger.exception(
                "Failed to render report to %s",
                self._report_path,
            )
