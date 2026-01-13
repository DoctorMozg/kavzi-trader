from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field

CROWDED_LONG_THRESHOLD = Decimal("2.0")
CROWDED_SHORT_THRESHOLD = Decimal("-2.0")
SQUEEZE_OI_THRESHOLD = Decimal("5.0")
SQUEEZE_PRICE_THRESHOLD = Decimal("0.5")


class FundingRateSchema(BaseModel):
    symbol: str
    funding_rate: Decimal
    funding_time: datetime
    mark_price: Decimal | None = None

    model_config = ConfigDict(frozen=True)


class OpenInterestSchema(BaseModel):
    symbol: str
    open_interest: Decimal
    timestamp: datetime

    model_config = ConfigDict(frozen=True)


class LongShortRatioSchema(BaseModel):
    symbol: str
    long_short_ratio: Decimal
    long_account_percent: Decimal
    short_account_percent: Decimal
    timestamp: datetime

    model_config = ConfigDict(frozen=True)


class FundingAnalysisSchema(BaseModel):
    funding_rate: Decimal
    funding_zscore: Decimal
    next_funding_time: datetime

    model_config = ConfigDict(frozen=True)


class OIMomentumSchema(BaseModel):
    open_interest: Decimal
    oi_change_1h_percent: Decimal
    oi_change_24h_percent: Decimal

    model_config = ConfigDict(frozen=True)


class OrderFlowSchema(BaseModel):
    symbol: str
    timestamp: datetime

    funding_rate: Decimal
    funding_zscore: Decimal
    next_funding_time: datetime

    open_interest: Decimal
    oi_change_1h_percent: Decimal
    oi_change_24h_percent: Decimal

    long_short_ratio: Decimal
    long_account_percent: Decimal
    short_account_percent: Decimal

    price_change_1h_percent: Decimal | None = None

    model_config = ConfigDict(frozen=True)

    @computed_field  # type: ignore[misc]
    @property
    def is_crowded_long(self) -> bool:
        return self.funding_zscore > CROWDED_LONG_THRESHOLD

    @computed_field  # type: ignore[misc]
    @property
    def is_crowded_short(self) -> bool:
        return self.funding_zscore < CROWDED_SHORT_THRESHOLD

    @computed_field  # type: ignore[misc]
    @property
    def squeeze_alert(self) -> bool:
        if self.price_change_1h_percent is None:
            return False
        return (
            abs(self.oi_change_1h_percent) > SQUEEZE_OI_THRESHOLD
            and abs(self.price_change_1h_percent) < SQUEEZE_PRICE_THRESHOLD
        )
