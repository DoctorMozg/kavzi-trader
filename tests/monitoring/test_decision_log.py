from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kavzi_trader.brain.schemas.decision import TradeDecisionSchema
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.monitoring.decision_log import DecisionLogWriter
from kavzi_trader.monitoring.decision_log_schema import DecisionLogSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema


@pytest.mark.asyncio
async def test_decision_log_writer(tmp_path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    indicators = TechnicalIndicatorsSchema(
        ema_20=None,
        ema_50=None,
        ema_200=None,
        sma_20=None,
        rsi_14=None,
        macd=None,
        bollinger=None,
        atr_14=Decimal(0),
        volume=None,
        timestamp=now,
    )
    order_flow = OrderFlowSchema(
        symbol="BTCUSDT",
        timestamp=now,
        funding_rate=Decimal(0),
        funding_zscore=Decimal(0),
        next_funding_time=now,
        open_interest=Decimal(0),
        oi_change_1h_percent=Decimal(0),
        oi_change_24h_percent=Decimal(0),
        long_short_ratio=Decimal(0),
        long_account_percent=Decimal(0),
        short_account_percent=Decimal(0),
    )
    decision = TradeDecisionSchema(
        action="WAIT",
        confidence=0.0,
        reasoning="skip",
        suggested_entry=None,
        suggested_stop_loss=None,
        suggested_take_profit=None,
        position_management=None,
        calibrated_confidence=0.0,
    )
    entry = DecisionLogSchema(
        timestamp=now,
        symbol="BTCUSDT",
        agent_tier="trader",
        indicators=indicators,
        order_flow=order_flow,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=0,
        raw_confidence=0.0,
        calibrated_confidence=0.0,
        decision=decision,
        raw_reasoning="skip",
    )
    log_path = tmp_path / "decisions.jsonl"
    writer = DecisionLogWriter(log_path)

    await writer.write(entry)

    content = log_path.read_text(encoding="utf-8")
    assert "BTCUSDT" in content
