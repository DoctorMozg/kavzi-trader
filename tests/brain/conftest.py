from decimal import Decimal

import pytest

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.algorithm_confluence_schema import (
    AlgorithmConfluenceSchema,
)
from kavzi_trader.spine.risk.schemas import VolatilityRegime
from kavzi_trader.spine.state.schemas import (
    AccountStateSchema,
    PositionManagementConfigSchema,
    PositionSchema,
)


@pytest.fixture
def candle() -> CandlestickSchema:
    now = utc_now()
    return CandlestickSchema(
        open_time=now,
        open_price=Decimal(100),
        high_price=Decimal(110),
        low_price=Decimal(95),
        close_price=Decimal(105),
        volume=Decimal(1000),
        close_time=now,
        quote_volume=Decimal(100000),
        trades_count=100,
        taker_buy_base_volume=Decimal(600),
        taker_buy_quote_volume=Decimal(60000),
        interval="15m",
        symbol="BTCUSDT",
    )


@pytest.fixture
def indicators() -> TechnicalIndicatorsSchema:
    return TechnicalIndicatorsSchema(
        ema_20=Decimal(100),
        ema_50=Decimal(98),
        ema_200=Decimal(90),
        sma_20=Decimal(99),
        rsi_14=Decimal(45),
        macd=None,
        bollinger=None,
        atr_14=Decimal(5),
        volume=None,
        timestamp=utc_now(),
    )


@pytest.fixture
def order_flow() -> OrderFlowSchema:
    return OrderFlowSchema(
        symbol="BTCUSDT",
        timestamp=utc_now(),
        funding_rate=Decimal("0.0001"),
        funding_zscore=Decimal("0.5"),
        next_funding_time=utc_now(),
        open_interest=Decimal(100000),
        oi_change_1h_percent=Decimal("1.0"),
        oi_change_24h_percent=Decimal("2.0"),
        long_short_ratio=Decimal("1.2"),
        long_account_percent=Decimal(60),
        short_account_percent=Decimal(40),
        price_change_1h_percent=Decimal("0.3"),
    )


@pytest.fixture
def algorithm_confluence() -> AlgorithmConfluenceSchema:
    return AlgorithmConfluenceSchema(
        ema_alignment=True,
        rsi_favorable=False,
        volume_above_average=True,
        price_at_bollinger=False,
        funding_favorable=True,
        oi_supports_direction=True,
        score=4,
    )


@pytest.fixture
def account_state() -> AccountStateSchema:
    now = utc_now()
    return AccountStateSchema(
        total_balance_usdt=Decimal(10000),
        available_balance_usdt=Decimal(8000),
        locked_balance_usdt=Decimal(2000),
        unrealized_pnl=Decimal(0),
        peak_balance=Decimal(10000),
        current_drawdown_percent=Decimal(0),
        updated_at=now,
    )


@pytest.fixture
def volatility_regime() -> VolatilityRegime:
    return VolatilityRegime.NORMAL


@pytest.fixture
def positions() -> list[PositionSchema]:
    now = utc_now()
    management = PositionManagementConfigSchema(
        trailing_stop_atr_multiplier=Decimal("1.5"),
        break_even_trigger_atr=Decimal("1.0"),
        partial_exit_at_percent=Decimal("0.5"),
        partial_exit_size=Decimal("0.3"),
        max_hold_time_hours=24,
        scale_in_allowed=False,
        scale_in_max_multiplier=Decimal("1.5"),
    )
    return [
        PositionSchema(
            id="pos-1",
            symbol="BTCUSDT",
            side="LONG",
            quantity=Decimal("0.1"),
            entry_price=Decimal(100),
            stop_loss=Decimal(95),
            take_profit=Decimal(120),
            current_stop_loss=Decimal(95),
            management_config=management,
            stop_loss_moved_to_breakeven=False,
            partial_exit_done=False,
            opened_at=now,
            updated_at=now,
        ),
    ]
