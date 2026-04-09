from decimal import Decimal

from kavzi_trader.commons.time_utility import utc_now
from kavzi_trader.order_flow.funding import calculate_funding_zscore
from kavzi_trader.order_flow.open_interest import (
    calculate_oi_momentum,
    periods_for_interval,
)
from kavzi_trader.order_flow.schemas import (
    FundingRateSchema,
    LongShortRatioSchema,
    OpenInterestSchema,
    OrderFlowSchema,
)


class OrderFlowCalculator:
    def __init__(self, interval_minutes: int = 15) -> None:
        self._periods_1h, self._periods_24h = periods_for_interval(interval_minutes)

    def calculate(
        self,
        symbol: str,
        funding_rates: list[FundingRateSchema],
        oi_history: list[OpenInterestSchema],
        long_short_ratio: LongShortRatioSchema | None = None,
        price_change_1h_percent: Decimal | None = None,
    ) -> OrderFlowSchema | None:
        funding_analysis = calculate_funding_zscore(funding_rates)
        if funding_analysis is None:
            return None

        oi_momentum = calculate_oi_momentum(
            oi_history,
            periods_1h=self._periods_1h,
            periods_24h=self._periods_24h,
        )
        if oi_momentum is None:
            return None

        ls_ratio = long_short_ratio or LongShortRatioSchema(
            symbol=symbol,
            long_short_ratio=Decimal("1.0"),
            long_account_percent=Decimal("50.0"),
            short_account_percent=Decimal("50.0"),
            timestamp=utc_now(),
        )

        return OrderFlowSchema(
            symbol=symbol,
            timestamp=utc_now(),
            funding_rate=funding_analysis.funding_rate,
            funding_zscore=funding_analysis.funding_zscore,
            next_funding_time=funding_analysis.next_funding_time,
            open_interest=oi_momentum.open_interest,
            oi_change_1h_percent=oi_momentum.oi_change_1h_percent,
            oi_change_24h_percent=oi_momentum.oi_change_24h_percent,
            long_short_ratio=ls_ratio.long_short_ratio,
            long_account_percent=ls_ratio.long_account_percent,
            short_account_percent=ls_ratio.short_account_percent,
            price_change_1h_percent=price_change_1h_percent,
        )
