from datetime import datetime
from decimal import Decimal

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.decision_message import DecisionMessageSchema
from kavzi_trader.domain.execution_result import ExecutionResultSchema
from kavzi_trader.domain.position_action import PositionActionSchema
from kavzi_trader.domain.scout_decision import ScoutDecisionSchema
from kavzi_trader.domain.state_schemas import AccountStateSchema, PositionSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema
from kavzi_trader.strategies.target_weight_intent_schema import (
    TargetWeightIntentSchema,
)
from kavzi_trader.strategies.trend.trend_gate_review_schema import (
    TrendGateReviewSchema,
)
from kavzi_trader.strategies.trend.trend_symbol_view_schema import (
    TrendSymbolViewSchema,
)
from kavzi_trader.strategies.trend.trend_view_schema import TrendViewSchema
from kavzi_trader.ui.event_schemas import (
    UiAccountEventSchema,
    UiCandleSchema,
    UiCandlesEventSchema,
    UiDecisionEventSchema,
    UiOpenPositionSchema,
    UiPositionClosedEventSchema,
    UiTradeEventSchema,
    UiTrendDaySchema,
    UiTrendStateEventSchema,
    UiTrendSymbolSchema,
)
from kavzi_trader.ui.publisher import UiPublisher


def _to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _now_ms() -> int:
    return _to_ms(utc_now())


def _trend_summary(symbol: TrendSymbolViewSchema, held_weight: float) -> str:
    if symbol.signal > 0:
        room = symbol.close / symbol.exit_level - 1
        return (
            f"Long at weight {held_weight:.3f}, close {symbol.close:,.6g}, "
            f"exits below {symbol.exit_level:,.6g} ({-room:+.1%})"
        )
    gap = symbol.entry_level / symbol.close - 1
    return (
        f"Flat, close {symbol.close:,.6g} needs to close above "
        f"{symbol.entry_level:,.6g} ({gap:+.1%})"
    )


def _gross_pnl(position: PositionSchema, price: Decimal) -> Decimal:
    move = price - position.entry_price
    return (
        move * position.quantity
        if position.side == "LONG"
        else -move * position.quantity
    )


class UiEventRecorder:
    """Translates trading-domain objects into dashboard events and publishes them."""

    def __init__(
        self,
        publisher: UiPublisher,
        initial_balance_usdt: Decimal,
        is_paper: bool,
        session_started_at_ms: int | None = None,
    ) -> None:
        self._publisher = publisher
        self._initial_balance_usdt = initial_balance_usdt
        self._is_paper = is_paper
        self._session_started_at_ms = session_started_at_ms or _now_ms()

    async def record_pipeline(
        self,
        symbol: str,
        scout: ScoutDecisionSchema,
        analyst: AnalystDecisionSchema | None,
        trader: TradeDecisionSchema | None,
        latency_ms: int,
    ) -> None:
        """Publish each stage reached; latency goes on the deepest stage only."""
        now_ms = _now_ms()
        events = [
            UiDecisionEventSchema(
                ts_ms=now_ms,
                symbol=symbol,
                stage="scout",
                verdict=scout.verdict,
                summary=scout.reason,
                reasoning=scout.pattern_detected,
            ),
        ]
        if analyst is not None:
            validity = "valid" if analyst.setup_valid else "invalid"
            events.append(
                UiDecisionEventSchema(
                    ts_ms=now_ms,
                    symbol=symbol,
                    stage="analyst",
                    verdict=analyst.direction if analyst.setup_valid else "INVALID",
                    summary=(
                        f"Setup {validity}, {analyst.direction}, "
                        f"confluence {analyst.confluence_score}/11"
                    ),
                    reasoning=analyst.reasoning,
                ),
            )
        if trader is not None:
            events.append(
                UiDecisionEventSchema(
                    ts_ms=now_ms,
                    symbol=symbol,
                    stage="trader",
                    verdict=trader.action,
                    summary=f"{trader.action}, confidence {trader.confidence:.0%}",
                    reasoning=trader.reasoning,
                    confidence=trader.confidence,
                ),
            )
        events[-1] = events[-1].model_copy(update={"latency_ms": latency_ms})
        for event in events:
            await self._publisher.publish(event)

    async def record_filter_rejection(
        self,
        symbol: str,
        action: str,
        reason: str,
        failed_filters: list[str],
    ) -> None:
        await self._publisher.publish(
            UiDecisionEventSchema(
                ts_ms=_now_ms(),
                symbol=symbol,
                stage="filter",
                verdict="BLOCKED",
                summary=f"Blocked {action}: {reason}",
                reasoning=f"Failed filters: {', '.join(failed_filters)}",
            ),
        )

    async def record_position_action(
        self,
        position: PositionSchema,
        action: PositionActionSchema,
    ) -> None:
        await self._publisher.publish(
            UiDecisionEventSchema(
                ts_ms=_now_ms(),
                symbol=position.symbol,
                stage="position",
                verdict=action.action.value,
                summary=action.reason,
            ),
        )

    async def record_trade(
        self,
        decision: DecisionMessageSchema,
        result: ExecutionResultSchema,
    ) -> None:
        quantity = (
            Decimal(str(result.executed_qty))
            if result.executed_qty
            else decision.quantity
        )
        await self._publisher.publish(
            UiTradeEventSchema(
                ts_ms=_now_ms(),
                symbol=decision.symbol,
                side=decision.action,
                status=result.status,
                confidence=decision.calibrated_confidence,
                entry_price=decision.entry_price,
                quantity=quantity,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
                reasoning=result.error_message or decision.reasoning,
            ),
        )

    async def record_position_close(
        self,
        position: PositionSchema,
        close_reason: str,
        exit_price: Decimal,
    ) -> None:
        await self._publisher.publish(
            UiPositionClosedEventSchema(
                ts_ms=_now_ms(),
                symbol=position.symbol,
                side=position.side,
                quantity=position.quantity,
                entry_price=position.entry_price,
                exit_price=exit_price,
                stop_loss=position.current_stop_loss,
                take_profit=position.take_profit,
                pnl_usdt=_gross_pnl(position, exit_price),
                close_reason=close_reason,
                leverage=position.leverage,
                opened_at_ms=_to_ms(position.opened_at),
            ),
        )

    async def record_account(
        self,
        account: AccountStateSchema,
        positions: list[PositionSchema],
        prices: dict[str, Decimal],
        running_loops: list[str],
    ) -> None:
        open_positions = []
        for position in positions:
            # Before the first tick for a symbol, entry is the only honest mark.
            mark = prices.get(position.symbol) or position.entry_price
            open_positions.append(
                UiOpenPositionSchema(
                    id=position.id,
                    symbol=position.symbol,
                    side=position.side,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    mark_price=mark,
                    stop_loss=position.current_stop_loss,
                    take_profit=position.take_profit,
                    unrealized_pnl_usdt=_gross_pnl(position, mark),
                    leverage=position.leverage,
                    opened_at_ms=_to_ms(position.opened_at),
                ),
            )
        await self._publisher.publish(
            UiAccountEventSchema(
                ts_ms=_now_ms(),
                session_started_at_ms=self._session_started_at_ms,
                is_paper=self._is_paper,
                initial_balance_usdt=self._initial_balance_usdt,
                balance_usdt=account.total_balance_usdt,
                unrealized_pnl_usdt=account.unrealized_pnl,
                positions=open_positions,
                prices=prices,
                running_loops=running_loops,
            ),
        )

    async def record_candles(
        self,
        symbol: str,
        interval: str,
        candles: list[CandlestickSchema],
    ) -> None:
        if not candles:
            return
        await self._publisher.publish(
            UiCandlesEventSchema(
                ts_ms=_now_ms(),
                symbol=symbol,
                interval=interval,
                candles=[
                    UiCandleSchema(
                        open_time_ms=_to_ms(c.open_time),
                        open=c.open_price,
                        high=c.high_price,
                        low=c.low_price,
                        close=c.close_price,
                        volume=c.volume,
                    )
                    for c in candles
                ],
            ),
        )

    async def record_trend_view(self, view: TrendViewSchema) -> None:
        """Publish the trend state, plus one feed entry per symbol on a rebalance."""
        now_ms = _now_ms()
        await self._publisher.publish(
            UiTrendStateEventSchema(
                ts_ms=now_ms,
                day=view.day,
                lookback=view.lookback,
                next_rebalance_ms=view.next_rebalance_ms,
                symbols=[
                    UiTrendSymbolSchema(
                        symbol=s.symbol,
                        signal=s.signal,
                        close=s.close,
                        entry_level=s.entry_level,
                        exit_level=s.exit_level,
                        annual_vol=s.annual_vol,
                        target_weight=view.target_weights[s.symbol],
                        held_weight=view.held_weights[s.symbol],
                        days=[
                            UiTrendDaySchema.model_validate(d.model_dump())
                            for d in s.days
                        ],
                    )
                    for s in view.symbols
                ],
                annual_vol_target=view.annual_vol_target,
                max_leverage=view.max_leverage,
                vol_window=view.vol_window,
                buffer_band=view.buffer_band,
                disaster_stop_pct=view.disaster_stop_pct,
            ),
        )
        if not view.rebalanced:
            return
        for symbol in view.symbols:
            await self._publisher.publish(
                UiDecisionEventSchema(
                    ts_ms=now_ms,
                    symbol=symbol.symbol,
                    stage="trend",
                    verdict="LONG" if symbol.signal > 0 else "FLAT",
                    summary=_trend_summary(symbol, view.held_weights[symbol.symbol]),
                ),
            )

    async def record_gate_review(self, review: TrendGateReviewSchema) -> None:
        vetoes = sum(s.verdict == "VETO" for s in review.samples)
        reasons = [s.reasoning for s in review.samples if s.verdict == review.decision]
        await self._publisher.publish(
            UiDecisionEventSchema(
                ts_ms=_now_ms(),
                symbol=review.symbol,
                stage="gate",
                verdict=review.decision,
                summary=(
                    f"Shadow news check: {vetoes}/{len(review.samples)} VETO, "
                    f"{review.coin_headlines} coin + {review.other_headlines} "
                    "other headlines"
                ),
                reasoning=reasons[0] if reasons else None,
            ),
        )

    async def record_rebalance(
        self,
        intent: TargetWeightIntentSchema,
        result: ExecutionResultSchema,
    ) -> None:
        await self._publisher.publish(
            UiTradeEventSchema(
                ts_ms=_now_ms(),
                symbol=intent.symbol,
                # The trend rule is long/flat, so a resize stays LONG.
                side="CLOSE" if intent.target_weight == 0 else "LONG",
                status=result.status,
                entry_price=result.executed_price,
                quantity=result.executed_qty,
                reasoning=result.error_message or intent.reason,
            ),
        )

    async def record_rebalance_skip(
        self,
        intent: TargetWeightIntentSchema,
        result: ExecutionResultSchema,
    ) -> None:
        """A target change the executor did not trade, with its reason."""
        await self._publisher.publish(
            UiDecisionEventSchema(
                ts_ms=_now_ms(),
                symbol=intent.symbol,
                stage="execution",
                verdict="NOT TRADED",
                summary=(
                    f"Target weight {float(intent.target_weight):.4f} not traded: "
                    f"{result.error_message or result.status}"
                ),
                reasoning=intent.reason or None,
            ),
        )
