from datetime import timedelta
from decimal import Decimal

import pytest

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.order_flow.schemas import (
    FundingRateSchema,
    LongShortRatioSchema,
    OpenInterestSchema,
)


@pytest.fixture()
def sample_funding_rates() -> list[FundingRateSchema]:
    base_time = utc_now()
    rates = [
        Decimal("0.0001"),
        Decimal("0.00012"),
        Decimal("0.00008"),
        Decimal("0.00015"),
        Decimal("0.0001"),
        Decimal("0.00011"),
        Decimal("0.00009"),
        Decimal("0.0002"),
        Decimal("0.00018"),
        Decimal("0.00022"),
    ]
    return [
        FundingRateSchema(
            symbol="BTCUSDT",
            funding_rate=rate,
            funding_time=base_time + timedelta(hours=8 * i),
            mark_price=Decimal("50000"),
        )
        for i, rate in enumerate(rates)
    ]


@pytest.fixture()
def sample_oi_history() -> list[OpenInterestSchema]:
    base_time = utc_now()
    oi_values = [
        Decimal("100000"),
        Decimal("102000"),
        Decimal("101500"),
        Decimal("103000"),
        Decimal("105000"),
        Decimal("104000"),
        Decimal("106000"),
        Decimal("108000"),
        Decimal("107500"),
        Decimal("110000"),
        Decimal("112000"),
        Decimal("115000"),
        Decimal("118000"),
    ]
    return [
        OpenInterestSchema(
            symbol="BTCUSDT",
            open_interest=oi,
            timestamp=base_time + timedelta(minutes=5 * i),
        )
        for i, oi in enumerate(oi_values)
    ]


@pytest.fixture()
def sample_long_short_ratio() -> LongShortRatioSchema:
    return LongShortRatioSchema(
        symbol="BTCUSDT",
        long_short_ratio=Decimal("1.25"),
        long_account_percent=Decimal("55.56"),
        short_account_percent=Decimal("44.44"),
        timestamp=utc_now(),
    )
