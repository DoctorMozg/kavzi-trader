from decimal import Decimal
from pathlib import Path

import pytest

from kavzi_trader.reporting.trade_report_populator import TradeReportPopulator


@pytest.fixture
def report_dir(tmp_path: Path) -> Path:
    return tmp_path / "reports"


@pytest.fixture
def populator(report_dir: Path) -> TradeReportPopulator:
    return TradeReportPopulator(
        report_dir=report_dir,
        initial_balance_usdt=Decimal(1000),
        max_action_entries=50,
        max_trade_entries=20,
    )


class TestTradeReportPopulator:
    def test_creates_directory_and_file_path(
        self,
        populator: TradeReportPopulator,
        report_dir: Path,
    ) -> None:
        assert report_dir.exists()
        assert populator.report_path.parent == report_dir
        assert populator.report_path.suffix == ".html"

    def test_initial_state(self, populator: TradeReportPopulator) -> None:
        state = populator.state
        assert state.initial_balance_usdt == Decimal(1000)
        assert state.current_balance_usdt == Decimal(1000)
        assert state.session_revenue_usdt == Decimal(0)
        assert state.version == 1
        assert state.actions == []
        assert state.trades == []

    @pytest.mark.asyncio
    async def test_record_action_appends(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        await populator.record_action(
            action_type="scout_scan",
            symbol="BTCUSDT",
            summary="Verdict: INTERESTING",
        )
        assert len(populator.state.actions) == 1
        assert populator.state.actions[0].symbol == "BTCUSDT"
        assert populator.state.version == 2

    @pytest.mark.asyncio
    async def test_record_action_writes_html(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        await populator.record_action(
            action_type="scout_scan",
            symbol="BTCUSDT",
            summary="test",
        )
        assert populator.report_path.exists()
        html = populator.report_path.read_text(encoding="utf-8")
        assert "BTCUSDT" in html
        assert "bootstrap" in html.lower()

    @pytest.mark.asyncio
    async def test_record_trade_appends(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        await populator.record_trade(
            symbol="ETHUSDT",
            side="BUY",
            status="FILLED",
            confidence=0.85,
            entry_price=Decimal(3500),
            quantity=Decimal("0.5"),
        )
        assert len(populator.state.trades) == 1
        assert populator.state.trades[0].side == "BUY"
        assert populator.state.version == 2

    @pytest.mark.asyncio
    async def test_record_trade_in_html(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        await populator.record_trade(
            symbol="BTCUSDT",
            side="SELL",
            status="REJECTED",
            confidence=0.6,
            reasoning="Risk too high",
        )
        html = populator.report_path.read_text(encoding="utf-8")
        assert "SELL" in html
        assert "REJECTED" in html

    @pytest.mark.asyncio
    async def test_update_balance(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        await populator.update_balance(
            current_balance_usdt=Decimal(1050),
            unrealized_pnl_usdt=Decimal(25),
            active_positions_count=2,
        )
        state = populator.state
        assert state.current_balance_usdt == Decimal(1050)
        assert state.session_revenue_usdt == Decimal(50)
        assert state.unrealized_pnl_usdt == Decimal(25)
        assert state.active_positions_count == 2

    @pytest.mark.asyncio
    async def test_version_increments(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        await populator.record_action(
            action_type="a",
            symbol="X",
            summary="s",
        )
        await populator.record_action(
            action_type="b",
            symbol="Y",
            summary="s",
        )
        await populator.record_trade(
            symbol="Z",
            side="BUY",
            status="FILLED",
            confidence=0.5,
        )
        assert populator.state.version == 4

    @pytest.mark.asyncio
    async def test_action_list_trimmed(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        for i in range(60):
            await populator.record_action(
                action_type="test",
                symbol="SYM",
                summary=f"entry {i}",
            )
        assert len(populator.state.actions) == 50

    @pytest.mark.asyncio
    async def test_trade_list_trimmed(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        for _i in range(25):
            await populator.record_trade(
                symbol="SYM",
                side="BUY",
                status="FILLED",
                confidence=0.5,
            )
        assert len(populator.state.trades) == 20

    @pytest.mark.asyncio
    async def test_html_contains_bootstrap_cdn(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        await populator.record_action(
            action_type="test",
            symbol="X",
            summary="s",
        )
        html = populator.report_path.read_text(encoding="utf-8")
        assert "cdn.jsdelivr.net/npm/bootstrap" in html

    @pytest.mark.asyncio
    async def test_html_contains_meta_refresh(
        self,
        populator: TradeReportPopulator,
    ) -> None:
        await populator.record_action(
            action_type="test",
            symbol="X",
            summary="s",
        )
        html = populator.report_path.read_text(encoding="utf-8")
        assert 'http-equiv="refresh"' in html
