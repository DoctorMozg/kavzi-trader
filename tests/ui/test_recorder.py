from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema, KeyLevelsSchema
from kavzi_trader.domain.execution_result import ExecutionResultSchema
from kavzi_trader.domain.position_action import PositionActionSchema
from kavzi_trader.domain.position_action_type import PositionActionType
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.state_schemas import (
    AccountStateSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)
from kavzi_trader.domain.trade_decision import TradeDecisionSchema
from kavzi_trader.domain.trend_gate_decision import TrendGateDecisionSchema
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from kavzi_trader.strategies.trend.trend_day_view_schema import TrendDayViewSchema
from kavzi_trader.strategies.trend.trend_gate_review_schema import (
    TrendGateReviewSchema,
)
from kavzi_trader.strategies.trend.trend_halving_schema import TrendHalvingSchema
from kavzi_trader.strategies.trend.trend_symbol_view_schema import (
    TrendSymbolViewSchema,
)
from kavzi_trader.strategies.trend.trend_view_schema import TrendViewSchema
from kavzi_trader.strategies.trend.vol_spike_config import VolSpikeConfigSchema
from kavzi_trader.strategies.trend.vol_spike_reading_schema import (
    VolSpikeReadingSchema,
)
from kavzi_trader.ui.event_schemas import (
    UiAccountEventSchema,
    UiDecisionEventSchema,
    UiPositionClosedEventSchema,
    UiTradeEventSchema,
    UiTrendStateEventSchema,
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


HALVING = TrendHalvingSchema(
    symbol="BTCUSDT",
    hour_ms=10 * 3_600_000,
    rv=0.003,
    threshold=0.001,
    target_weight=0.025,
)


def _trend_view(rebalanced: bool) -> TrendViewSchema:
    days = [
        TrendDayViewSchema(
            day_ms=0, close=100.0, upper=110.0, lower=90.0, exit=100.0, signal=1.0
        )
    ]
    return TrendViewSchema(
        day=date(2026, 11, 17),
        lookback=20,
        exit_rule="mid",
        check_hours=6,
        next_rebalance_ms=2_000,
        rebalanced=rebalanced,
        symbols=[
            TrendSymbolViewSchema(
                symbol="BTCUSDT",
                signal=1.0,
                close=100.0,
                entry_level=100.0,
                exit_level=80.0,
                annual_vol=0.6,
                days=days,
            ),
            TrendSymbolViewSchema(
                symbol="ETHUSDT",
                signal=0.0,
                close=50.0,
                entry_level=60.0,
                exit_level=45.0,
                days=days,
            ),
        ],
        target_weights={"BTCUSDT": 0.06, "ETHUSDT": 0.0},
        held_weights={"BTCUSDT": 0.05, "ETHUSDT": 0.0},
        annual_vol_target=0.25,
        max_leverage=2.0,
        vol_window=30,
        buffer_band=0.2,
        disaster_stop_pct=0.3,
        vol_spike=VolSpikeConfigSchema(),
        spikes={
            "BTCUSDT": VolSpikeReadingSchema(
                hour_ms=HALVING.hour_ms, rv=0.003, threshold=0.001
            )
        },
        halvings={"BTCUSDT": HALVING},
    )


class TestRecordTrend:
    async def test_rebalanced_view_publishes_state_and_one_entry_per_symbol(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        await recorder.record_trend_view(_trend_view(rebalanced=True))

        state, btc, eth = publisher.events
        assert isinstance(state, UiTrendStateEventSchema)
        assert [(s.symbol, s.target_weight, s.held_weight) for s in state.symbols] == [
            ("BTCUSDT", 0.06, 0.05),
            ("ETHUSDT", 0.0, 0.0),
        ]
        assert (state.annual_vol_target, state.buffer_band) == (0.25, 0.2)
        assert isinstance(btc, UiDecisionEventSchema)
        assert isinstance(eth, UiDecisionEventSchema)
        assert (btc.stage, btc.verdict) == ("trend", "LONG")
        assert "exits below 80" in btc.summary
        assert (eth.stage, eth.verdict) == ("trend", "FLAT")
        assert "above 60 (+20.0%)" in eth.summary

    async def test_restart_view_publishes_state_only(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        await recorder.record_trend_view(_trend_view(rebalanced=False))

        (state,) = publisher.events
        assert isinstance(state, UiTrendStateEventSchema)

    async def test_exit_rule_spikes_and_halvings_reach_the_dashboard(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        await recorder.record_trend_view(_trend_view(rebalanced=False))

        (state,) = publisher.events
        assert isinstance(state, UiTrendStateEventSchema)
        btc, eth = state.symbols
        assert state.exit_rule == "mid"
        assert state.vol_spike is not None
        assert (state.vol_spike.quantile, state.vol_spike.scale) == (0.99, 0.5)
        assert btc.days[0].exit == 100.0
        assert btc.spike is not None
        assert btc.spike.threshold == 0.001
        assert btc.halving is not None
        assert btc.halving.target_weight == 0.025
        assert (eth.spike, eth.halving) == (None, None)

    async def test_halving_becomes_a_trend_decision(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        await recorder.record_halving(HALVING)

        (event,) = publisher.events
        assert isinstance(event, UiDecisionEventSchema)
        assert (event.symbol, event.stage, event.verdict) == (
            "BTCUSDT",
            "trend",
            "HALVE",
        )
        assert "10:00 UTC" in event.summary
        assert "3.0x its threshold" in event.summary

    async def test_gate_review_becomes_gate_decision_with_majority_reason(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
    ) -> None:
        veto = TrendGateDecisionSchema(
            verdict="VETO",
            catalyst="exploit",
            reasoning="Bridge exploit drained funds.",
        )
        keep = TrendGateDecisionSchema(
            verdict="KEEP", catalyst="none", reasoning="No coin-specific negative news."
        )
        review = TrendGateReviewSchema(
            symbol="SOLUSDT",
            as_of=OPENED_AT,
            decision="VETO",
            samples=[keep, veto, veto],
            coin_headlines=3,
            other_headlines=27,
            prompt_sha="abc",
        )

        await recorder.record_gate_review(review)

        (event,) = publisher.events
        assert isinstance(event, UiDecisionEventSchema)
        assert (event.stage, event.verdict) == ("gate", "VETO")
        assert "2/3 VETO, 3 coin + 27 other" in event.summary
        assert event.reasoning == veto.reasoning

    @pytest.mark.parametrize(
        ("weight", "side"), [(Decimal("0.05"), "LONG"), (Decimal(0), "CLOSE")]
    )
    async def test_rebalance_fill_becomes_trade_without_confidence(
        self,
        recorder: UiEventRecorder,
        publisher: CollectingUiPublisher,
        weight: Decimal,
        side: str,
    ) -> None:
        intent = TargetWeightIntentSchema(
            strategy="trend_following",
            intent_id="tw-1",
            symbol="BTCUSDT",
            target_weight=weight,
            disaster_stop_pct=Decimal("0.3"),
            created_at_ms=1,
            expires_at_ms=2,
            reason="weight 0.0000 -> 0.0500",
        )
        result = ExecutionResultSchema(
            decision_id="tw-1",
            order_id="7",
            status="FILLED",
            executed_qty=Decimal("0.01"),
            executed_price=Decimal(65000),
        )

        await recorder.record_rebalance(intent, result)

        (event,) = publisher.events
        assert isinstance(event, UiTradeEventSchema)
        assert (event.side, event.status, event.confidence) == (side, "FILLED", None)
        assert event.entry_price == Decimal(65000)
        assert event.reasoning == "weight 0.0000 -> 0.0500"
