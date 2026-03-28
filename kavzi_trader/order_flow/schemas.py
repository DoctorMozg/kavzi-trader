from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field

CROWDED_LONG_THRESHOLD = Decimal("2.0")
CROWDED_SHORT_THRESHOLD = Decimal("-2.0")
SQUEEZE_OI_THRESHOLD = Decimal("5.0")
SQUEEZE_PRICE_THRESHOLD = Decimal("0.5")
DIVERGENCE_OI_THRESHOLD = Decimal("2.0")
DIVERGENCE_FUNDING_ZSCORE = Decimal("1.0")


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

    @computed_field  # type: ignore[misc]
    @property
    def oi_funding_divergence(self) -> bool:
        """Rising OI + negative funding OR falling OI + positive funding."""
        rising_oi = self.oi_change_1h_percent > DIVERGENCE_OI_THRESHOLD
        falling_oi = self.oi_change_1h_percent < -DIVERGENCE_OI_THRESHOLD
        negative_funding = self.funding_zscore < -DIVERGENCE_FUNDING_ZSCORE
        positive_funding = self.funding_zscore > DIVERGENCE_FUNDING_ZSCORE
        return (rising_oi and negative_funding) or (falling_oi and positive_funding)

    @computed_field  # type: ignore[misc]
    @property
    def oi_funding_divergence_direction(self) -> str | None:
        """Contrarian direction implied by the divergence.

        LONG: rising OI + negative funding (shorts entering → contrarian bullish).
        SHORT: falling OI + positive funding (longs exiting → contrarian bearish).
        """
        if not self.oi_funding_divergence:
            return None
        rising_oi = self.oi_change_1h_percent > DIVERGENCE_OI_THRESHOLD
        negative_funding = self.funding_zscore < -DIVERGENCE_FUNDING_ZSCORE
        if rising_oi and negative_funding:
            return "LONG"
        return "SHORT"
