from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.schemas import (
    BollingerBandsSchema,
    TechnicalIndicatorsSchema,
    VolumeAnalysisSchema,
)
from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.state.schemas import (
    PositionManagementConfigSchema,
    PositionSchema,
)


@pytest.fixture()
def filter_config() -> FilterConfigSchema:
    return FilterConfigSchema()


@pytest.fixture()
def sample_candle() -> CandlestickSchema:
    now = datetime.now(UTC)
    return CandlestickSchema(
        open_time=now - timedelta(minutes=5),
        open_price=Decimal("100"),
        high_price=Decimal("105"),
        low_price=Decimal("95"),
        close_price=Decimal("102"),
        volume=Decimal("1000"),
        close_time=now,
        quote_volume=Decimal("100000"),
        trades_count=100,
        taker_buy_base_volume=Decimal("500"),
        taker_buy_quote_volume=Decimal("50000"),
        interval="5m",
        symbol="BTCUSDT",
    )


@pytest.fixture()
def sample_indicators() -> TechnicalIndicatorsSchema:
    now = datetime.now(UTC)
    return TechnicalIndicatorsSchema(
        ema_20=Decimal("101"),
        ema_50=Decimal("100"),
        ema_200=Decimal("98"),
        sma_20=Decimal("100"),
        rsi_14=Decimal("35"),
        macd=None,
        bollinger=BollingerBandsSchema(
            upper=Decimal("110"),
            middle=Decimal("100"),
            lower=Decimal("95"),
            width=Decimal("0.1"),
            percent_b=Decimal("0.2"),
        ),
        atr_14=Decimal("5"),
        volume=VolumeAnalysisSchema(
            current_volume=Decimal("1200"),
            average_volume=Decimal("1000"),
            volume_ratio=Decimal("1.2"),
            obv=None,
        ),
        timestamp=now,
    )


@pytest.fixture()
def sample_order_flow() -> OrderFlowSchema:
    now = datetime.now(UTC)
    return OrderFlowSchema(
        symbol="BTCUSDT",
        timestamp=now,
        funding_rate=Decimal("0.01"),
        funding_zscore=Decimal("1.0"),
        next_funding_time=now + timedelta(hours=8),
        open_interest=Decimal("1000000"),
        oi_change_1h_percent=Decimal("2.0"),
        oi_change_24h_percent=Decimal("5.0"),
        long_short_ratio=Decimal("1.1"),
        long_account_percent=Decimal("55"),
        short_account_percent=Decimal("45"),
        price_change_1h_percent=Decimal("0.4"),
    )


@pytest.fixture()
def sample_positions() -> list[PositionSchema]:
    now = datetime.now(UTC)
    return [
        PositionSchema(
            id="pos-1",
            symbol="ETHUSDT",
            side="LONG",
            quantity=Decimal("1"),
            entry_price=Decimal("2000"),
            stop_loss=Decimal("1900"),
            take_profit=Decimal("2200"),
            current_stop_loss=Decimal("1900"),
            management_config=PositionManagementConfigSchema(),
            opened_at=now,
            updated_at=now,
        ),
    ]
