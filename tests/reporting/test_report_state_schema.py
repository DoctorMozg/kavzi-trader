from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from kavzi_trader.reporting.report_state_schema import (
    ReportActionEntrySchema,
    ReportStateSchema,
    ReportTradeEntrySchema,
)


def _now() -> datetime:
    return datetime.now(UTC)


class TestReportActionEntrySchema:
    def test_valid_construction(self) -> None:
        entry = ReportActionEntrySchema(
            timestamp=_now(),
            action_type="scout_scan",
            symbol="BTCUSDT",
            summary="Verdict: INTERESTING",
        )
        assert entry.action_type == "scout_scan"
        assert entry.details is None

    def test_with_details(self) -> None:
        entry = ReportActionEntrySchema(
            timestamp=_now(),
            action_type="analyst_review",
            symbol="ETHUSDT",
            summary="Valid: True",
            details="Direction: LONG, Confluence: 7",
        )
        assert entry.details is not None

    def test_frozen(self) -> None:
        entry = ReportActionEntrySchema(
            timestamp=_now(),
            action_type="scout_scan",
            symbol="BTCUSDT",
            summary="test",
        )
        with pytest.raises(ValidationError):
            entry.symbol = "ETHUSDT"  # type: ignore[misc]


class TestReportTradeEntrySchema:
    def test_valid_construction(self) -> None:
        entry = ReportTradeEntrySchema(
            timestamp=_now(),
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            confidence=0.85,
        )
        assert entry.side == "BUY"
        assert entry.entry_price is None

    def test_full_fields(self) -> None:
        entry = ReportTradeEntrySchema(
            timestamp=_now(),
            symbol="ETHUSDT",
            side="SELL",
            entry_price=Decimal("3500.00"),
            quantity=Decimal("0.5"),
            stop_loss=Decimal("3600.00"),
            take_profit=Decimal("3200.00"),
            status="SUBMITTED",
            confidence=0.72,
            reasoning="Strong downtrend",
        )
        assert entry.entry_price == Decimal("3500.00")
        assert entry.reasoning == "Strong downtrend"

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReportTradeEntrySchema(
                timestamp=_now(),
                symbol="BTCUSDT",
                side="LONG",  # type: ignore[arg-type]
                status="FILLED",
                confidence=0.5,
            )

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ReportTradeEntrySchema(
                timestamp=_now(),
                symbol="BTCUSDT",
                side="BUY",
                status="FILLED",
                confidence=1.5,
            )


class TestReportStateSchema:
    def _make_state(self) -> ReportStateSchema:
        now = _now()
        return ReportStateSchema(
            session_started_at=now,
            last_updated_at=now,
            initial_balance_usdt=Decimal(1000),
            current_balance_usdt=Decimal(1000),
        )

    def test_defaults(self) -> None:
        state = self._make_state()
        assert state.version == 1
        assert state.session_revenue_usdt == Decimal(0)
        assert state.unrealized_pnl_usdt == Decimal(0)
        assert state.active_positions_count == 0
        assert state.actions == []
        assert state.trades == []

    def test_model_copy_updates_version(self) -> None:
        state = self._make_state()
        updated = state.model_copy(update={"version": 2})
        assert updated.version == 2
        assert state.version == 1

    def test_model_copy_appends_action(self) -> None:
        state = self._make_state()
        entry = ReportActionEntrySchema(
            timestamp=_now(),
            action_type="scout_scan",
            symbol="BTCUSDT",
            summary="test",
        )
        updated = state.model_copy(
            update={"actions": [*state.actions, entry]},
        )
        assert len(updated.actions) == 1
        assert len(state.actions) == 0

    def test_json_serialization(self) -> None:
        state = self._make_state()
        dumped = state.model_dump(mode="json")
        assert isinstance(dumped["initial_balance_usdt"], str)
        assert isinstance(dumped["session_started_at"], str)

    def test_frozen(self) -> None:
        state = self._make_state()
        with pytest.raises(ValidationError):
            state.version = 99  # type: ignore[misc]
