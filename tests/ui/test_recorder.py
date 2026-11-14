from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kavzi_trader.brain.schemas.analyst import AnalystDecisionSchema, KeyLevelsSchema
from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.brain.schemas.scout import ScoutDecisionSchema
from kavzi_trader.spine.position.position_action_schema import PositionActionSchema
from kavzi_trader.spine.position.position_action_type import PositionActionType
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.ui.event_schemas import (
    UiAccountEventSchema,
    UiDecisionEventSchema,
    UiPositionClosedEventSchema,
)
from kavzi_trader.ui.recorder import UiEventRecorder
from tests.ui.factories import CollectingUiPublisher

OPENED_AT = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
REASONING = "Momentum confirmed on the close with expanding volume and clean structure."


def _position(side: str = "SHORT", symbol: str = "DOGEUSDT") -> PositionSchema:
    return PositionSchema.model_validate(
        {
            "id": "pos-1",
            "symbol": symbol,
            "side": side,
            "quantity": Decimal(86207),
            "entry_price": Decimal("0.09055"),
            "stop_loss": Decimal("0.09112"),
            "take_profit": Decimal("0.08942"),
            "current_stop_loss": Decimal("0.09080"),
            "management_config": PositionManagementConfigSchema(),
            "leverage": 3,
            "opened_at": OPENED_AT,
            "updated_at": OPENED_AT,
        },
    )


def _account() -> AccountStateSchema:
    return AccountStateSchema(
        total_balance_usdt=Decimal(1010),
        available_balance_usdt=Decimal(900),
        locked_balance_usdt=Decimal(110),
        unrealized_pnl=Decimal("40.5"),
        peak_balance=Decimal(1010),
        updated_at=OPENED_AT,
    )


@pytest.fixture
def publisher() -> CollectingUiPublisher:
    return CollectingUiPublisher()


@pytest.fixture
def recorder(publisher: CollectingUiPublisher) -> UiEventRecorder:
    return UiEventRecorder(
        publisher,
        initial_balance_usdt=Decimal(1000),
        is_paper=True,
        session_started_at_ms=1_000,
    )


class TestRecordPipeline:
    async def test_scout_only_carries_latency(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        scout = ScoutDecisionSchema(verdict="SKIP", reason="Flat range")

        await recorder.record_pipeline("BTCUSDT", scout, None, None, latency_ms=3)

        assert len(publisher.events) == 1
        event = publisher.events[0]
        assert isinstance(event, UiDecisionEventSchema)
        assert (event.stage, event.verdict, event.latency_ms) == ("scout", "SKIP", 3)

    async def test_full_pipeline_latency_on_trader_only(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        scout = ScoutDecisionSchema(verdict="INTERESTING", reason="Breakout")
        analyst = AnalystDecisionSchema(
            setup_valid=False,
            direction="LONG",
            confluence_score=5,
            key_levels=KeyLevelsSchema(levels=[]),
            reasoning=REASONING + " Extra context to pass the length gate.",
        )
        trader = TradeDecisionSchema(
            action="WAIT", confidence=0.42, reasoning=REASONING
        )

        await recorder.record_pipeline(
            "BTCUSDT", scout, analyst, trader, latency_ms=4200
        )

        decisions = [
            e for e in publisher.events if isinstance(e, UiDecisionEventSchema)
        ]
        assert [d.stage for d in decisions] == ["scout", "analyst", "trader"]
        assert decisions[1].verdict == "INVALID"
        assert decisions[2].confidence == pytest.approx(0.42)
        assert [d.latency_ms for d in decisions] == [None, None, 4200]


class TestRecordPositions:
    async def test_close_computes_short_pnl_and_uses_current_stop(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        await recorder.record_position_close(
            _position(),
            "take_profit",
            Decimal("0.09008"),
        )

        event = publisher.events[0]
        assert isinstance(event, UiPositionClosedEventSchema)
        assert event.pnl_usdt == (Decimal("0.09055") - Decimal("0.09008")) * 86207
        assert event.stop_loss == Decimal("0.09080")
        assert event.opened_at_ms == int(OPENED_AT.timestamp() * 1000)

    async def test_account_marks_positions_and_falls_back_to_entry(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        positions = [_position("LONG", "BTCUSDT"), _position("SHORT", "DOGEUSDT")]

        await recorder.record_account(
            _account(),
            positions,
            prices={"BTCUSDT": Decimal("0.09155")},
            running_loops=["ingest"],
        )

        event = publisher.events[0]
        assert isinstance(event, UiAccountEventSchema)
        btc, doge = event.positions
        assert btc.unrealized_pnl_usdt == Decimal("0.00100") * 86207
        assert doge.mark_price == doge.entry_price
        assert doge.unrealized_pnl_usdt == 0
        assert event.initial_balance_usdt == Decimal(1000)
        assert event.session_started_at_ms == 1_000

    async def test_position_action_becomes_position_stage_decision(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        action = PositionActionSchema(
            action=PositionActionType.PARTIAL_EXIT,
            reason="Reached 1R",
        )

        await recorder.record_position_action(_position(), action)

        event = publisher.events[0]
        assert isinstance(event, UiDecisionEventSchema)
        assert (event.stage, event.verdict, event.summary) == (
            "position",
            "PARTIAL_EXIT",
            "Reached 1R",
        )
